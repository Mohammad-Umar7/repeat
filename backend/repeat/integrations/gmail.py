"""Gmail API via google-api-python-client. The sync client is run in a worker thread."""

from __future__ import annotations

import asyncio
import base64
import re
from pathlib import Path

from ..models import EmailContext, UndoToken
from .base import ActionResult, GmailClient, IntegrationError, VerifyResult

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def _header(headers: list[dict], name: str) -> str:
    return next((h["value"] for h in headers if h["name"].lower() == name.lower()), "")


def _plain_body(payload: dict) -> str:
    stack = [payload]
    html = ""
    while stack:
        part = stack.pop()
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and mime == "text/plain":
            return base64.urlsafe_b64decode(data).decode("utf-8", "replace")
        if data and mime == "text/html" and not html:
            html = base64.urlsafe_b64decode(data).decode("utf-8", "replace")
        stack.extend(part.get("parts", []))
    text = re.sub(r"<(script|style).*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>|</p>|</div>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _split_sender(raw: str) -> tuple[str, str | None]:
    m = re.match(r"\s*\"?([^\"<]*)\"?\s*<([^>]+)>", raw)
    if m:
        return m.group(2).strip(), (m.group(1).strip() or None)
    return raw.strip(), None


class LiveGmailClient(GmailClient):
    def __init__(self, *, credentials_file: Path, token_file: Path, handled_label: str) -> None:
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.handled_label = handled_label
        self._service = None
        self._label_ids: dict[str, str] = {}

    # ── auth ──────────────────────────────────────────────────────────

    def _build(self):
        if self._service:
            return self._service
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if self.token_file.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_file.exists():
                    raise IntegrationError(
                        f"Gmail OAuth client file missing at {self.credentials_file}.",
                        retryable=False,
                    )
                flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_file), SCOPES)
                creds = flow.run_local_server(port=0)
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            self.token_file.write_text(creds.to_json(), encoding="utf-8")
        self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return self._service

    async def _run(self, fn, *a, **kw):
        try:
            return await asyncio.to_thread(fn, *a, **kw)
        except IntegrationError:
            raise
        except Exception as e:
            raise IntegrationError(f"Gmail call failed: {e}") from e

    async def health(self) -> tuple[bool, str]:
        try:
            prof = await self._run(lambda: self._build().users().getProfile(userId="me").execute())
            return True, f"Gmail connected as {prof.get('emailAddress')}"
        except Exception as e:
            return False, f"Gmail unreachable: {e}"

    # ── read ──────────────────────────────────────────────────────────

    def _to_context(self, msg: dict) -> EmailContext:
        headers = msg["payload"].get("headers", [])
        sender, name = _split_sender(_header(headers, "From"))
        return EmailContext(
            id=msg["id"],
            thread_id=msg.get("threadId"),
            subject=_header(headers, "Subject") or "(no subject)",
            sender=sender,
            sender_name=name,
            body=_plain_body(msg["payload"]),
            received_at=_header(headers, "Date") or None,
            labels=msg.get("labelIds", []),
        )

    async def latest_email(self) -> EmailContext | None:
        def _fetch():
            svc = self._build()
            res = (
                svc.users().messages().list(userId="me", labelIds=["INBOX"], maxResults=1).execute()
            )
            ids = res.get("messages", [])
            if not ids:
                return None
            return svc.users().messages().get(userId="me", id=ids[0]["id"], format="full").execute()

        msg = await self._run(_fetch)
        return self._to_context(msg) if msg else None

    async def get_email(self, message_id: str) -> EmailContext | None:
        def _fetch():
            svc = self._build()
            return svc.users().messages().get(userId="me", id=message_id, format="full").execute()

        try:
            msg = await self._run(_fetch)
        except IntegrationError as e:
            if "404" in str(e):
                return None
            raise
        return self._to_context(msg)

    # ── labels ────────────────────────────────────────────────────────

    def _label_id(self, name: str) -> str:
        if name in self._label_ids:
            return self._label_ids[name]
        svc = self._build()
        for lb in svc.users().labels().list(userId="me").execute().get("labels", []):
            self._label_ids[lb["name"]] = lb["id"]
        if name not in self._label_ids:
            created = (
                svc.users()
                .labels()
                .create(
                    userId="me",
                    body={
                        "name": name,
                        "labelListVisibility": "labelShow",
                        "messageListVisibility": "show",
                    },
                )
                .execute()
            )
            self._label_ids[name] = created["id"]
        return self._label_ids[name]

    async def apply_label(self, message_id: str, label: str) -> ActionResult:
        def _do():
            svc = self._build()
            lid = self._label_id(label)
            svc.users().messages().modify(
                userId="me", id=message_id, body={"addLabelIds": [lid]}
            ).execute()
            return lid

        lid = await self._run(_do)
        return ActionResult(
            outputs={"label": label, "label_id": lid},
            undo_token=UndoToken(
                kind="gmail_label", ref={"message_id": message_id, "label": label}
            ),
            result_url=f"https://mail.google.com/mail/u/0/#inbox/{message_id}",
        )

    async def verify_label(self, message_id: str, label: str) -> VerifyResult:
        def _check():
            svc = self._build()
            lid = self._label_id(label)
            msg = svc.users().messages().get(userId="me", id=message_id, format="minimal").execute()
            return lid in msg.get("labelIds", [])

        ok = await self._run(_check)
        return VerifyResult(ok, f"Label {label} {'present' if ok else 'missing'} on the email.")

    async def remove_label(self, message_id: str, label: str) -> VerifyResult:
        def _do():
            svc = self._build()
            lid = self._label_id(label)
            svc.users().messages().modify(
                userId="me", id=message_id, body={"removeLabelIds": [lid]}
            ).execute()

        await self._run(_do)
        check = await self.verify_label(message_id, label)
        return VerifyResult(
            not check.ok, "Label removed and confirmed." if not check.ok else "Label still present."
        )
