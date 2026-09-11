"""Demo-mode sandbox. Stateful in-memory Jira, Slack and Gmail with realistic IDs.

This is what makes the two-minute demo deterministic on stage. It behaves like the
real APIs (create -> verify -> delete -> verify-gone), including latency, so the
timeline, undo slider and verification checks exercise the real code paths.
"""

from __future__ import annotations

import asyncio
import itertools
import time
from datetime import UTC, datetime

from ..models import EmailContext, UndoToken
from .base import (
    ActionResult,
    GmailClient,
    IntegrationError,
    JiraClient,
    SlackClient,
    VerifyResult,
)

LATENCY = 0.35  # seconds, so the ghost fill and checks are visible but snappy


class SandboxJira(JiraClient):
    def __init__(self, project_key: str, base_url: str = "https://demo.atlassian.net") -> None:
        self.project_key = project_key
        self.base_url = base_url
        self.issues: dict[str, dict] = {}
        self._seq = itertools.count(142)
        self.fail_next: str | None = None  # test hook for the paused state

    def reset(self) -> None:
        self.issues.clear()
        self._seq = itertools.count(142)
        self.fail_next = None

    async def health(self) -> tuple[bool, str]:
        return True, f"Jira sandbox ({self.project_key}), {len(self.issues)} issues"

    async def create_issue(self, *, summary: str, description: str) -> ActionResult:
        await asyncio.sleep(LATENCY)
        if self.fail_next:
            msg, self.fail_next = self.fail_next, None
            raise IntegrationError(msg)
        key = f"{self.project_key}-{next(self._seq)}"
        self.issues[key] = {
            "key": key,
            "summary": summary,
            "description": description,
            "status": "To Do",
            "created": datetime.now(UTC).isoformat(),
        }
        url = f"{self.base_url}/browse/{key}"
        return ActionResult(
            outputs={"issue_key": key, "issue_url": url, "issue_id": str(10000 + len(self.issues))},
            undo_token=UndoToken(kind="jira_issue", ref={"key": key}),
            result_url=url,
        )

    async def verify_issue(self, key: str) -> VerifyResult:
        await asyncio.sleep(LATENCY / 2)
        if key in self.issues:
            return VerifyResult(
                True, f"{key} exists (To Do)", {"summary": self.issues[key]["summary"]}
            )
        return VerifyResult(False, f"{key} was not found in Jira.")

    async def delete_issue(self, key: str) -> VerifyResult:
        await asyncio.sleep(LATENCY)
        self.issues.pop(key, None)
        return VerifyResult(True, f"{key} deleted and confirmed gone.")


class SandboxSlack(SlackClient):
    def __init__(self, channel: str) -> None:
        self.channel_name = channel.lstrip("#")
        self.channel_id = "C0DEM0CHAN"
        self.messages: dict[str, dict] = {}
        self.fail_next: str | None = None

    def reset(self) -> None:
        self.messages.clear()
        self.fail_next = None

    async def health(self) -> tuple[bool, str]:
        return True, f"Slack sandbox (#{self.channel_name}), {len(self.messages)} messages"

    async def post_message(self, *, channel: str, text: str) -> ActionResult:
        await asyncio.sleep(LATENCY)
        if self.fail_next:
            msg, self.fail_next = self.fail_next, None
            raise IntegrationError(msg)
        ts = f"{time.time():.6f}"
        self.messages[ts] = {"ts": ts, "text": text, "channel": self.channel_id}
        link = f"https://demo.slack.com/archives/{self.channel_id}/p{ts.replace('.', '')}"
        return ActionResult(
            outputs={"slack_ts": ts, "slack_channel_id": self.channel_id, "slack_permalink": link},
            undo_token=UndoToken(
                kind="slack_message", ref={"channel_id": self.channel_id, "ts": ts}
            ),
            result_url=link,
        )

    async def verify_message(self, channel_id: str, ts: str) -> VerifyResult:
        await asyncio.sleep(LATENCY / 2)
        if ts in self.messages:
            return VerifyResult(
                True, "Message is live in Slack.", {"text": self.messages[ts]["text"]}
            )
        return VerifyResult(False, "Message not found in channel history.")

    async def delete_message(self, channel_id: str, ts: str) -> VerifyResult:
        await asyncio.sleep(LATENCY)
        self.messages.pop(ts, None)
        return VerifyResult(True, "Slack message deleted and confirmed gone.")


DEMO_EMAILS: list[EmailContext] = [
    EmailContext(
        id="demo-mail-001",
        thread_id="demo-thread-001",
        subject="Checkout button does nothing on Safari 17",
        sender="priya.nair@northwind.io",
        sender_name="Priya Nair",
        body=(
            "Hi team,\n\n"
            "Since this morning the Checkout button on the cart page does nothing on Safari 17 "
            "(macOS 14.5). Clicking it shows a brief spinner and then the page stays on the "
            "cart.\n\n"
            "Steps to reproduce:\n"
            "1. Add any item to the cart\n"
            "2. Open the cart page in Safari 17\n"
            "3. Click Checkout\n\n"
            "Expected: redirected to payment.\n"
            "Actual: spinner, then nothing. "
            "Console shows TypeError: window.__stripe is undefined.\n\n"
            "Chrome works fine. About 12 customers have written in so far.\n\n"
            "Thanks,\nPriya"
        ),
        received_at=datetime.now(UTC).isoformat(),
        labels=["INBOX", "UNREAD"],
    ),
    EmailContext(
        id="demo-mail-002",
        thread_id="demo-thread-002",
        subject="Export to CSV truncates rows past 10,000",
        sender="marcus.lee@fabrikam.com",
        sender_name="Marcus Lee",
        body=(
            "Hello,\n\nExporting the transactions report to CSV silently stops at row 10,000. "
            "The UI says 14,312 rows. No error is shown.\n\n"
            "Steps: Reports > Transactions > Export CSV on the Q2 range.\n"
            "Expected: 14,312 rows. Actual: 10,000 rows.\n\nMarcus"
        ),
        received_at=datetime.now(UTC).isoformat(),
        labels=["INBOX", "UNREAD"],
    ),
    EmailContext(
        id="demo-mail-003",
        thread_id="demo-thread-003",
        subject="Lunch on Thursday?",
        sender="sam@friends.example",
        sender_name="Sam",
        body="Hey! Are you free for lunch Thursday? The new ramen place opened.",
        received_at=datetime.now(UTC).isoformat(),
        labels=["INBOX"],
    ),
]


class SandboxGmail(GmailClient):
    def __init__(self, handled_label: str) -> None:
        self.handled_label = handled_label
        self.emails: dict[str, EmailContext] = {}
        self.reset()

    def reset(self) -> None:
        self.emails = {e.id: e.model_copy(deep=True) for e in DEMO_EMAILS}

    async def health(self) -> tuple[bool, str]:
        return True, f"Gmail sandbox, {len(self.emails)} emails"

    async def latest_email(self) -> EmailContext | None:
        await asyncio.sleep(LATENCY / 2)
        return next(iter(self.emails.values()), None)

    async def get_email(self, message_id: str) -> EmailContext | None:
        return self.emails.get(message_id)

    async def apply_label(self, message_id: str, label: str) -> ActionResult:
        await asyncio.sleep(LATENCY)
        email = self.emails.get(message_id)
        if not email:
            raise IntegrationError("That email no longer exists in the inbox.", retryable=False)
        if label not in email.labels:
            email.labels.append(label)
        return ActionResult(
            outputs={"label": label, "label_id": "Label_42"},
            undo_token=UndoToken(
                kind="gmail_label", ref={"message_id": message_id, "label": label}
            ),
            result_url=f"https://mail.google.com/mail/u/0/#inbox/{message_id}",
        )

    async def verify_label(self, message_id: str, label: str) -> VerifyResult:
        await asyncio.sleep(LATENCY / 2)
        email = self.emails.get(message_id)
        ok = bool(email and label in email.labels)
        return VerifyResult(ok, f"Label {label} {'present' if ok else 'missing'} on the email.")

    async def remove_label(self, message_id: str, label: str) -> VerifyResult:
        await asyncio.sleep(LATENCY)
        email = self.emails.get(message_id)
        if email and label in email.labels:
            email.labels.remove(label)
        return VerifyResult(True, "Label removed and confirmed.")
