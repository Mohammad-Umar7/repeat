"""Integration contracts. Every target app implements: do, verify, undo.

The agent never talks to an app any other way. That is what makes every action
previewable (the plan is data), verifiable (verify is separate from do), and
reversible (undo takes the token do returned).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..models import EmailContext, UndoToken


class IntegrationError(RuntimeError):
    """Human-readable, one sentence. This text is shown in the paused state."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass
class ActionResult:
    outputs: dict[str, Any]
    undo_token: UndoToken
    result_url: str | None = None


@dataclass
class VerifyResult:
    ok: bool
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)


class JiraClient(ABC):
    @abstractmethod
    async def create_issue(self, *, summary: str, description: str) -> ActionResult: ...

    @abstractmethod
    async def verify_issue(self, key: str) -> VerifyResult: ...

    @abstractmethod
    async def delete_issue(self, key: str) -> VerifyResult: ...

    @abstractmethod
    async def health(self) -> tuple[bool, str]: ...


class SlackClient(ABC):
    @abstractmethod
    async def post_message(self, *, channel: str, text: str) -> ActionResult: ...

    @abstractmethod
    async def verify_message(self, channel_id: str, ts: str) -> VerifyResult: ...

    @abstractmethod
    async def delete_message(self, channel_id: str, ts: str) -> VerifyResult: ...

    @abstractmethod
    async def health(self) -> tuple[bool, str]: ...


class GmailClient(ABC):
    @abstractmethod
    async def latest_email(self) -> EmailContext | None: ...

    @abstractmethod
    async def get_email(self, message_id: str) -> EmailContext | None: ...

    @abstractmethod
    async def apply_label(self, message_id: str, label: str) -> ActionResult: ...

    @abstractmethod
    async def verify_label(self, message_id: str, label: str) -> VerifyResult: ...

    @abstractmethod
    async def remove_label(self, message_id: str, label: str) -> VerifyResult: ...

    @abstractmethod
    async def health(self) -> tuple[bool, str]: ...


@dataclass
class Integrations:
    jira: JiraClient
    slack: SlackClient
    gmail: GmailClient
    mode: str  # "live" | "sandbox"
