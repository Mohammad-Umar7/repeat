"""Domain models shared by the store, the agent and the HTTP API.

Everything the extension records, everything the agent learns, and everything
a run produces is one of these. They are deliberately plain so they serialise
to JSON columns in SQLite without translation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ── Recorded events (Teach mode) ─────────────────────────────────────────


class EventKind(StrEnum):
    copy = "copy"
    paste = "paste"
    input = "input"
    click = "click"
    navigate = "navigate"
    narration = "narration"


class RecordedEvent(BaseModel):
    """One semantic event captured by the extension's recorder content script."""

    kind: EventKind
    ts: float = Field(description="Unix ms timestamp from the browser")
    url: str
    title: str = ""
    app: str = Field(default="unknown", description="gmail | jira | slack | unknown")
    # copy / paste
    text: str | None = None
    # input
    field_label: str | None = None
    field_name: str | None = None
    value: str | None = None
    # click
    target_text: str | None = None
    target_role: str | None = None
    # narration
    transcript: str | None = None


class Demonstration(BaseModel):
    id: str = Field(default_factory=lambda: new_id("demo"))
    created_at: str = Field(default_factory=now_iso)
    events: list[RecordedEvent] = Field(default_factory=list)
    narration: list[RecordedEvent] = Field(default_factory=list)
    workflow_id: str | None = None


# ── Learned workflow template ─────────────────────────────────────────────


class Trigger(BaseModel):
    app: Literal["gmail"] = "gmail"
    description: str = Field(description="Plain-English description of the triggering email")
    subject_keywords: list[str] = Field(default_factory=list)
    body_keywords: list[str] = Field(default_factory=list)
    sender_pattern: str | None = None


class Variable(BaseModel):
    name: str = Field(description="snake_case identifier used inside step templates as {name}")
    source: str = Field(
        description="Where the value comes from, e.g. email.subject, step:create_issue.key"
    )
    description: str = ""


class StepAction(StrEnum):
    jira_create_issue = "jira.create_issue"
    slack_post_message = "slack.post_message"
    gmail_apply_label = "gmail.apply_label"


class WorkflowStep(BaseModel):
    id: str
    action: StepAction
    app: Literal["jira", "slack", "gmail"]
    title: str = Field(description="Short human title shown on the timeline")
    fields: dict[str, str] = Field(
        description="Field name -> template string using {variable} placeholders"
    )
    produces: list[str] = Field(
        default_factory=list, description="Variables this step yields, e.g. issue_key"
    )


class Workflow(BaseModel):
    id: str = Field(default_factory=lambda: new_id("wf"))
    name: str
    created_at: str = Field(default_factory=now_iso)
    demonstration_id: str | None = None
    trigger: Trigger
    variables: list[Variable]
    steps: list[WorkflowStep]
    estimated_manual_seconds: int = Field(
        default=240, description="How long the human task takes; drives the time-saved counter"
    )
    run_count: int = 0


# ── Runs (Ghost mode + Undo) ───────────────────────────────────────────────


class EmailContext(BaseModel):
    id: str
    thread_id: str | None = None
    subject: str
    sender: str
    sender_name: str | None = None
    body: str
    received_at: str | None = None
    labels: list[str] = Field(default_factory=list)


class StepStatus(StrEnum):
    planned = "planned"
    previewing = "previewing"
    running = "running"
    verifying = "verifying"
    done = "done"
    failed = "failed"
    skipped = "skipped"
    reverting = "reverting"
    reverted = "reverted"
    revert_failed = "revert_failed"


class UndoToken(BaseModel):
    """Enough to reverse the step through the API later, and nothing more."""

    kind: Literal["jira_issue", "slack_message", "gmail_label"]
    ref: dict[str, Any]


class RunStep(BaseModel):
    id: str
    workflow_step_id: str
    action: StepAction
    app: str
    title: str
    status: StepStatus = StepStatus.planned
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    verification: dict[str, Any] | None = None
    undo_token: UndoToken | None = None
    error: str | None = None
    attempts: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    reverted_at: str | None = None
    result_url: str | None = None


class RiskSummary(BaseModel):
    external_messages: int
    records_created: int
    records_modified: int
    records_deleted: int
    blast_radius: str = Field(description="One plain-English line")
    level: Literal["low", "medium", "high"]


class RunStatus(StrEnum):
    no_match = "no_match"
    matched = "matched"
    planned = "planned"
    awaiting_approval = "awaiting_approval"
    running = "running"
    paused = "paused"
    completed = "completed"
    stopped = "stopped"
    failed = "failed"
    reverted = "reverted"
    partially_reverted = "partially_reverted"


class Run(BaseModel):
    id: str = Field(default_factory=lambda: new_id("run"))
    workflow_id: str
    workflow_name: str
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    status: RunStatus = RunStatus.matched
    email: EmailContext
    match_confidence: float = 0.0
    match_reason: str = ""
    variables: dict[str, Any] = Field(default_factory=dict)
    risk: RiskSummary | None = None
    steps: list[RunStep] = Field(default_factory=list)
    current_step: int = 0
    pause_reason: str | None = None
    seconds_saved: int = 0
    undo_cursor: int = Field(
        default=0, description="Number of steps currently committed (slider position)"
    )

    def touch(self) -> None:
        self.updated_at = now_iso()
