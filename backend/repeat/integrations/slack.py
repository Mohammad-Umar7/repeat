"""Slack Web API with a bot token. Channel names are resolved to IDs once and cached."""

from __future__ import annotations

import httpx

from ..models import UndoToken
from .base import ActionResult, IntegrationError, SlackClient, VerifyResult


class LiveSlackClient(SlackClient):
    def __init__(self, *, bot_token: str) -> None:
        self._client = httpx.AsyncClient(
            base_url="https://slack.com/api",
            headers={"Authorization": f"Bearer {bot_token}"},
            timeout=20,
        )
        self._channel_ids: dict[str, str] = {}

    async def _call(self, method: str, **params) -> dict:
        try:
            r = await self._client.post(f"/{method}", json=params)
        except httpx.HTTPError as e:
            raise IntegrationError(f"Slack did not respond ({e}).") from e
        data = r.json()
        if not data.get("ok"):
            err = data.get("error", "unknown_error")
            retryable = err in {"ratelimited", "internal_error", "service_unavailable"}
            raise IntegrationError(f"Slack error: {err}.", retryable=retryable)
        return data

    async def health(self) -> tuple[bool, str]:
        try:
            d = await self._call("auth.test")
            return True, f"Slack connected to {d.get('team')} as {d.get('user')}"
        except Exception as e:
            return False, f"Slack unreachable: {e}"

    async def resolve_channel(self, channel: str) -> str:
        if channel.startswith(("C", "G")) and channel.isupper():
            return channel
        name = channel.lstrip("#")
        if name in self._channel_ids:
            return self._channel_ids[name]
        cursor = None
        while True:
            d = await self._call(
                "conversations.list",
                types="public_channel,private_channel",
                limit=200,
                exclude_archived=True,
                **({"cursor": cursor} if cursor else {}),
            )
            for ch in d.get("channels", []):
                self._channel_ids[ch["name"]] = ch["id"]
            cursor = d.get("response_metadata", {}).get("next_cursor") or None
            if name in self._channel_ids or not cursor:
                break
        if name not in self._channel_ids:
            raise IntegrationError(f"Slack channel #{name} was not found.", retryable=False)
        return self._channel_ids[name]

    async def post_message(self, *, channel: str, text: str) -> ActionResult:
        channel_id = await self.resolve_channel(channel)
        d = await self._call("chat.postMessage", channel=channel_id, text=text, unfurl_links=False)
        ts = d["ts"]
        link = None
        try:
            p = await self._call("chat.getPermalink", channel=channel_id, message_ts=ts)
            link = p.get("permalink")
        except IntegrationError:
            pass
        return ActionResult(
            outputs={"slack_ts": ts, "slack_channel_id": channel_id, "slack_permalink": link},
            undo_token=UndoToken(kind="slack_message", ref={"channel_id": channel_id, "ts": ts}),
            result_url=link,
        )

    async def verify_message(self, channel_id: str, ts: str) -> VerifyResult:
        try:
            d = await self._call(
                "conversations.history", channel=channel_id, latest=ts, oldest=ts, inclusive=True, limit=1
            )
        except IntegrationError as e:
            return VerifyResult(False, str(e))
        msgs = d.get("messages", [])
        if msgs and msgs[0].get("ts") == ts:
            return VerifyResult(True, "Message is live in Slack.", {"text": msgs[0].get("text")})
        return VerifyResult(False, "Message not found in channel history.")

    async def delete_message(self, channel_id: str, ts: str) -> VerifyResult:
        try:
            await self._call("chat.delete", channel=channel_id, ts=ts)
        except IntegrationError as e:
            if "message_not_found" not in str(e):
                return VerifyResult(False, str(e))
        check = await self.verify_message(channel_id, ts)
        if not check.ok:
            return VerifyResult(True, "Slack message deleted and confirmed gone.")
        return VerifyResult(False, "Slack message still present after delete.")
