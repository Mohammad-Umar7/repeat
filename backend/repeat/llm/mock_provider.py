"""Deterministic provider used when no OpenAI key is configured.

It does real work (keyword extraction, template filling) so the demo path is
believable and never depends on the network. It is not a stub: outputs are
derived from the actual input text.
"""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel

from ..agent.schemas import (
    GeneralizedStep,
    GeneralizedVariable,
    GeneralizeOutput,
    MatchOutput,
    PlannedValue,
    PlanOutput,
    RiskOutput,
)
from .base import LLMError, LLMProvider

T = TypeVar("T", bound=BaseModel)

_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "it", "this",
    "that", "with", "when", "we", "i", "you", "at", "by", "from", "be", "as", "are",
}


def _keywords(text: str, limit: int = 5) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", text.lower())
    seen: list[str] = []
    for w in words:
        if w not in _STOP and w not in seen:
            seen.append(w)
        if len(seen) >= limit:
            break
    return seen


def _payload(user: str) -> dict:
    """Prompts embed their data as a JSON block after a `DATA:` marker."""
    if "DATA:" not in user:
        return {}
    try:
        return json.loads(user.split("DATA:", 1)[1].strip())
    except json.JSONDecodeError:
        return {}


class MockProvider(LLMProvider):
    name = "mock"

    async def complete_structured(
        self, *, system: str, user: str, schema: type[T], temperature: float = 0.0
    ) -> T:
        data = _payload(user)
        if schema is GeneralizeOutput:
            return self._generalize(data)  # type: ignore[return-value]
        if schema is MatchOutput:
            return self._match(data)  # type: ignore[return-value]
        if schema is PlanOutput:
            return self._plan(data)  # type: ignore[return-value]
        if schema is RiskOutput:
            return self._risk(data)  # type: ignore[return-value]
        raise LLMError(f"mock provider has no strategy for {schema.__name__}")

    async def transcribe(self, audio_bytes: bytes, filename: str = "narration.webm") -> str:
        return ""

    # ── strategies ────────────────────────────────────────────────────

    def _generalize(self, data: dict) -> GeneralizeOutput:
        events = data.get("events", [])
        apps = [e.get("app") for e in events]
        subject = next(
            (e.get("text") for e in events if e.get("kind") == "copy" and e.get("app") == "gmail"),
            "",
        ) or ""
        steps: list[GeneralizedStep] = []
        if "jira" in apps:
            steps.append(
                GeneralizedStep(
                    action="jira.create_issue",
                    title="Create Jira issue",
                    field_names=["summary", "description", "reporter_note"],
                    field_templates=[
                        "{email_subject}",
                        "{email_body}",
                        "Reported by {reporter} via email",
                    ],
                    produces=["issue_key", "issue_url"],
                )
            )
        if "slack" in apps:
            steps.append(
                GeneralizedStep(
                    action="slack.post_message",
                    title="Post to Slack",
                    field_names=["text"],
                    field_templates=[
                        "New bug from {reporter}: *{email_subject}* → {issue_key} {issue_url}"
                    ],
                    produces=["slack_ts"],
                )
            )
        steps.append(
            GeneralizedStep(
                action="gmail.apply_label",
                title="Label email as handled",
                field_names=["label"],
                field_templates=["REPEAT/handled"],
                produces=[],
            )
        )
        return GeneralizeOutput(
            name="Bug email to Jira and Slack" if "jira" in apps else "Email to Slack",
            trigger_description="A bug report email arrives in the inbox",
            subject_keywords=_keywords(subject) or ["bug", "error", "broken"],
            body_keywords=["steps", "reproduce", "expected", "actual"],
            variables=[
                GeneralizedVariable(name="email_subject", source="email.subject", description="Subject line"),
                GeneralizedVariable(name="email_body", source="email.body", description="Plain-text body"),
                GeneralizedVariable(name="reporter", source="email.sender", description="Sender address"),
                GeneralizedVariable(name="issue_key", source="step:create_issue.key", description="Jira key"),
                GeneralizedVariable(name="issue_url", source="step:create_issue.url", description="Jira link"),
            ],
            steps=steps,
            estimated_manual_seconds=240,
        )

    def _match(self, data: dict) -> MatchOutput:
        email = data.get("email", {})
        trigger = data.get("trigger", {})
        hay = f"{email.get('subject','')} {email.get('body','')}".lower()
        subj_hits = [k for k in trigger.get("subject_keywords", []) if k.lower() in hay]
        body_hits = [k for k in trigger.get("body_keywords", []) if k.lower() in hay]
        score = min(1.0, 0.35 * len(subj_hits) + 0.15 * len(body_hits))
        generic = any(w in hay for w in ("bug", "error", "broken", "crash", "fail", "not working"))
        if generic:
            score = max(score, 0.82)
        matched = score >= 0.6
        reason = (
            f"Subject and body look like a bug report ({', '.join(subj_hits + body_hits) or 'bug language'})."
            if matched
            else "Email does not read like a bug report."
        )
        return MatchOutput(matches=matched, confidence=round(score, 2), reason=reason)

    def _plan(self, data: dict) -> PlanOutput:
        email = data.get("email", {})
        values = [
            PlannedValue(name="email_subject", value=email.get("subject", "")),
            PlannedValue(name="email_body", value=(email.get("body", "") or "")[:1500]),
            PlannedValue(name="reporter", value=email.get("sender_name") or email.get("sender", "")),
        ]
        return PlanOutput(values=values, notes="Mapped subject, body and sender directly from the email.")

    def _risk(self, data: dict) -> RiskOutput:
        steps = data.get("steps", [])
        created = sum(1 for s in steps if s.get("action") == "jira.create_issue")
        msgs = sum(1 for s in steps if s.get("action") == "slack.post_message")
        modified = sum(1 for s in steps if s.get("action") == "gmail.apply_label")
        channel = data.get("slack_channel", "product-updates")
        parts = []
        if created:
            parts.append(f"Creates {created} Jira issue{'s' if created != 1 else ''}")
        if msgs:
            parts.append(f"posts {msgs} message{'s' if msgs != 1 else ''} to #{channel}")
        if modified:
            parts.append("labels 1 email")
        parts.append("no external emails, no payments")
        return RiskOutput(
            external_messages=msgs,
            records_created=created,
            records_modified=modified,
            records_deleted=0,
            blast_radius=", ".join(parts) + ".",
            level="low" if msgs <= 1 and created <= 1 else "medium",
        )
