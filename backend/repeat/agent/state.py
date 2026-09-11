"""LangGraph state for the two graphs.

TeachState flows through observe -> generalize -> record_workflow.
RunState flows through match -> plan -> assess_risk -> await_approval ->
(execute -> verify -> record)* with gates for step-by-step commits and failures.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from ..models import Demonstration, EmailContext, Run, Workflow


class Failure(TypedDict):
    node: str
    message: str
    retryable: bool


class TeachState(TypedDict, total=False):
    demonstration: Demonstration
    normalized: list[dict[str, Any]]
    workflow: Workflow | None
    failure: Failure | None
    decision: Literal["retry", "stop"] | None
    failure_origin: str
    stopped: bool


class RunState(TypedDict, total=False):
    workflow: Workflow
    email: EmailContext
    run: Run
    mode: Literal["step", "all"]
    matched: bool
    failure: Failure | None
    decision: Literal["retry", "skip", "stop"] | None
    failure_origin: str
    stopped: bool
    step_started_at: float
