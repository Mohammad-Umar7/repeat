"""Agent nodes. Every node follows the same contract:

  * do one thing,
  * persist the Run/Workflow and publish an event so the panel is never stale,
  * on failure: set state["failure"] with a ONE-SENTENCE explanation and return.
    The graph routes to a gate that pauses and offers retry / skip / stop.
    Nothing is ever silently continued.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any

from langgraph.types import interrupt

from ..deps import get_deps
from ..integrations.base import ActionResult, IntegrationError, VerifyResult
from ..llm.base import LLMError
from ..models import (
    RiskSummary,
    Run,
    RunStatus,
    RunStep,
    StepAction,
    StepStatus,
    Trigger,
    Variable,
    Workflow,
    WorkflowStep,
    now_iso,
)
from ..prompts import render
from .schemas import GeneralizeOutput, MatchOutput, PlanOutput, RiskOutput
from .state import Failure, RunState, TeachState

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


def _fail(node: str, message: str, retryable: bool = True) -> Failure:
    log.warning("node %s failed: %s", node, message)
    return {"node": node, "message": message, "retryable": retryable}


async def _save(run: Run, event: str = "run.updated", extra: dict | None = None) -> None:
    d = get_deps()
    await d.store.save_run(run)
    await d.bus.publish(event, {"run": run.model_dump(mode="json"), **(extra or {})})


def fill_template(template: str, variables: dict[str, Any]) -> str:
    def sub(m: re.Match) -> str:
        return str(variables.get(m.group(1), m.group(0)))

    return re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", sub, template)


# ═════════════════════════════════════════════════════════════════════
# Teach graph
# ═════════════════════════════════════════════════════════════════════


async def observe(state: TeachState) -> TeachState:
    """Normalise the raw event stream: drop noise, dedupe, attach narration by time."""
    demo = state["demonstration"]
    events = sorted(demo.events, key=lambda e: e.ts)
    narration = sorted(demo.narration, key=lambda e: e.ts)
    out: list[dict[str, Any]] = []
    last_input: dict | None = None
    for e in events:
        row = e.model_dump(mode="json", exclude_none=True)
        # collapse successive input events on the same field to the final value
        if e.kind.value == "input" and last_input and last_input.get("field_label") == e.field_label:
            last_input["value"] = e.value
            last_input["ts"] = e.ts
            continue
        if e.kind.value == "input":
            last_input = row
        else:
            last_input = None
        if e.kind.value == "click" and not (e.target_text or "").strip():
            continue
        out.append(row)
    for n in narration:
        nearest = min(out, key=lambda r: abs(r["ts"] - n.ts), default=None)
        if nearest is not None and abs(nearest["ts"] - n.ts) < 8000:
            nearest.setdefault("narration", []).append(n.transcript or n.text or "")
    if not out:
        return {"failure": _fail("observe", "No usable events were recorded; try the demonstration again.", False)}
    return {"normalized": out, "failure": None}


async def generalize(state: TeachState) -> TeachState:
    d = get_deps()
    demo = state["demonstration"]
    system, user = render("generalize", {"events": state["normalized"]})
    try:
        g: GeneralizeOutput = await d.llm.complete_structured(
            system=system, user=user, schema=GeneralizeOutput
        )
    except LLMError as e:
        return {"failure": _fail("generalize", f"The model could not generalise the demonstration ({e}).")}
    steps: list[WorkflowStep] = []
    for i, s in enumerate(g.steps):
        app = s.action.split(".")[0]
        fields = dict(zip(s.field_names, s.field_templates))
        steps.append(
            WorkflowStep(
                id=f"s{i + 1}_{s.action.split('.')[1]}",
                action=StepAction(s.action),
                app=app,  # type: ignore[arg-type]
                title=s.title,
                fields=fields,
                produces=s.produces,
            )
        )
    if not steps:
        return {"failure": _fail("generalize", "The model produced a workflow with no steps.")}
    wf = Workflow(
        name=g.name,
        demonstration_id=demo.id,
        trigger=Trigger(
            description=g.trigger_description,
            subject_keywords=g.subject_keywords,
            body_keywords=g.body_keywords,
        ),
        variables=[Variable(**v.model_dump()) for v in g.variables],
        steps=steps,
        estimated_manual_seconds=max(30, g.estimated_manual_seconds),
    )
    return {"workflow": wf, "failure": None}


async def record_workflow(state: TeachState) -> TeachState:
    d = get_deps()
    wf = state["workflow"]
    demo = state["demonstration"]
    assert wf is not None
    demo.workflow_id = wf.id
    try:
        await d.store.save_workflow(wf)
        await d.store.save_demonstration(demo)
    except Exception as e:
        return {"failure": _fail("record", f"Could not save the workflow locally ({e}).")}
    await d.bus.publish("workflow.learned", {"workflow": wf.model_dump(mode="json")})
    return {"failure": None}


async def teach_failure_gate(state: TeachState) -> TeachState:
    f = state.get("failure")
    assert f
    decision = interrupt({"type": "failure", "node": f["node"], "message": f["message"],
                          "options": ["retry", "stop"] if f["retryable"] else ["stop"]})
    choice = (decision or {}).get("decision", "stop")
    if choice == "retry" and f["retryable"]:
        return {"decision": "retry", "failure": None}
    return {"decision": "stop", "stopped": True}


# ═════════════════════════════════════════════════════════════════════
# Run graph
# ═════════════════════════════════════════════════════════════════════


async def match(state: RunState) -> RunState:
    d = get_deps()
    wf, email, run = state["workflow"], state["email"], state["run"]
    system, user = render(
        "match", {"trigger": wf.trigger.model_dump(), "email": email.model_dump(exclude={"labels"})}
    )
    try:
        m: MatchOutput = await d.llm.complete_structured(system=system, user=user, schema=MatchOutput)
    except LLMError as e:
        run.status = RunStatus.stopped
        run.match_reason = f"Could not evaluate this email ({e})."
        await _save(run, "run.no_match")
        return {"matched": False, "run": run, "stopped": True}
    run.match_confidence = m.confidence
    run.match_reason = m.reason
    if not m.matches:
        run.status = RunStatus.stopped
        await _save(run, "run.no_match")
        return {"matched": False, "run": run, "stopped": True}
    run.status = RunStatus.matched
    await _save(run, "run.matched")
    return {"matched": True, "run": run, "failure": None}


async def plan(state: RunState) -> RunState:
    d = get_deps()
    wf, email, run = state["workflow"], state["email"], state["run"]
    email_vars = [v.model_dump() for v in wf.variables if v.source.startswith("email.")]
    system, user = render("plan", {"variables": email_vars, "email": email.model_dump(exclude={"labels"})})
    try:
        p: PlanOutput = await d.llm.complete_structured(system=system, user=user, schema=PlanOutput)
        values = {v.name: v.value for v in p.values}
    except LLMError as e:
        return {"failure": _fail("plan", f"The model could not fill the variables ({e}).")}
    # guarantee every email-sourced variable has a value even if the model skipped one
    direct = {"email.subject": email.subject, "email.body": email.body, "email.sender": email.sender_name or email.sender}
    for v in wf.variables:
        if v.source in direct and not values.get(v.name):
            values[v.name] = direct[v.source]
    run.variables = values
    run.steps = [
        RunStep(
            id=f"{run.id}_{s.id}",
            workflow_step_id=s.id,
            action=s.action,
            app=s.app,
            title=s.title,
            inputs={k: fill_template(t, values) for k, t in s.fields.items()},
        )
        for s in wf.steps
    ]
    run.status = RunStatus.planned
    await _save(run, "run.planned")
    return {"run": run, "failure": None}


async def assess_risk(state: RunState) -> RunState:
    d = get_deps()
    run = state["run"]
    system, user = render(
        "assess_risk",
        {
            "steps": [{"action": s.action.value, "app": s.app, "inputs": s.inputs} for s in run.steps],
            "slack_channel": d.settings.slack_channel,
        },
    )
    try:
        r: RiskOutput = await d.llm.complete_structured(system=system, user=user, schema=RiskOutput)
    except LLMError as e:
        return {"failure": _fail("assess_risk", f"The model could not compute the risk summary ({e}).")}
    run.risk = RiskSummary(**r.model_dump())
    run.status = RunStatus.awaiting_approval
    await _save(run, "run.awaiting_approval")
    return {"run": run, "failure": None}


async def await_approval(state: RunState) -> RunState:
    """Human-in-the-loop. Interrupt with the risk summary; resume with the user's decision."""
    run = state["run"]
    decision = interrupt(
        {
            "type": "approval",
            "run_id": run.id,
            "risk": run.risk.model_dump() if run.risk else None,
            "options": ["step", "all", "dismiss"],
        }
    )
    choice = (decision or {}).get("decision", "dismiss")
    if choice == "dismiss":
        run.status = RunStatus.stopped
        run.pause_reason = "Dismissed before the first commit."
        await _save(run, "run.stopped")
        return {"run": run, "stopped": True}
    run.status = RunStatus.running
    await _save(run, "run.approved", {"mode": choice})
    return {"run": run, "mode": "all" if choice == "all" else "step"}


async def step_gate(state: RunState) -> RunState:
    """In step mode, wait for Tab (commit) or Esc (stop) before each step after the first."""
    run = state["run"]
    idx = run.current_step
    step = run.steps[idx]
    step.status = StepStatus.previewing
    await _save(run, "step.previewing", {"step_index": idx})
    decision = interrupt(
        {"type": "step_gate", "run_id": run.id, "step_index": idx,
         "step": step.model_dump(mode="json"), "options": ["commit", "all", "stop"]}
    )
    choice = (decision or {}).get("decision", "stop")
    if choice == "stop":
        step.status = StepStatus.planned
        run.status = RunStatus.stopped
        run.pause_reason = f"Stopped before '{step.title}'."
        await _save(run, "run.stopped")
        return {"run": run, "stopped": True}
    return {"run": run, "mode": "all" if choice == "all" else "step"}


async def _do_action(run: Run, step: RunStep) -> ActionResult:
    d = get_deps()
    i = d.integrations
    if step.action == StepAction.jira_create_issue:
        desc = step.inputs.get("description", "")
        note = step.inputs.get("reporter_note")
        if note:
            desc = f"{desc}\n\n{note}"
        return await i.jira.create_issue(summary=step.inputs.get("summary", "(no summary)"), description=desc)
    if step.action == StepAction.slack_post_message:
        return await i.slack.post_message(
            channel=step.inputs.get("channel") or d.settings.slack_channel, text=step.inputs.get("text", "")
        )
    if step.action == StepAction.gmail_apply_label:
        return await i.gmail.apply_label(run.email.id, step.inputs.get("label") or d.settings.gmail_handled_label)
    raise IntegrationError(f"Unknown action {step.action}.", retryable=False)


async def execute(state: RunState) -> RunState:
    run = state["run"]
    idx = run.current_step
    step = run.steps[idx]
    # re-fill inputs now: earlier steps may have produced variables (issue_key)
    wf_step = next(s for s in state["workflow"].steps if s.id == step.workflow_step_id)
    step.inputs = {k: fill_template(t, run.variables) for k, t in wf_step.fields.items()}
    step.status = StepStatus.running
    step.attempts += 1
    step.started_at = step.started_at or now_iso()
    step.error = None
    run.status = RunStatus.running
    await _save(run, "step.running", {"step_index": idx})
    try:
        result = await _do_action(run, step)
    except IntegrationError as e:
        step.status = StepStatus.failed
        step.error = str(e)
        run.status = RunStatus.paused
        run.pause_reason = str(e)
        await _save(run, "step.failed", {"step_index": idx})
        retryable = e.retryable and step.attempts < MAX_ATTEMPTS
        return {"run": run, "failure": _fail("execute", str(e), retryable)}
    step.outputs = result.outputs
    step.undo_token = result.undo_token
    step.result_url = result.result_url
    run.variables.update(result.outputs)
    await _save(run, "step.executed", {"step_index": idx})
    return {"run": run, "failure": None, "step_started_at": time.time()}


async def _do_verify(run: Run, step: RunStep) -> VerifyResult:
    i = get_deps().integrations
    tok = step.undo_token
    if not tok:
        return VerifyResult(False, "No undo token was recorded, so the result cannot be verified.")
    if tok.kind == "jira_issue":
        return await i.jira.verify_issue(tok.ref["key"])
    if tok.kind == "slack_message":
        return await i.slack.verify_message(tok.ref["channel_id"], tok.ref["ts"])
    if tok.kind == "gmail_label":
        return await i.gmail.verify_label(tok.ref["message_id"], tok.ref["label"])
    return VerifyResult(False, f"Unknown undo token kind {tok.kind}.")


async def verify(state: RunState) -> RunState:
    run = state["run"]
    idx = run.current_step
    step = run.steps[idx]
    step.status = StepStatus.verifying
    await _save(run, "step.verifying", {"step_index": idx})
    try:
        v = await _do_verify(run, step)
    except Exception as e:  # network blip while checking
        v = VerifyResult(False, f"Could not confirm the result ({e}).")
    step.verification = {"ok": v.ok, "detail": v.detail, "evidence": v.evidence}
    if not v.ok:
        step.status = StepStatus.failed
        step.error = v.detail
        run.status = RunStatus.paused
        run.pause_reason = f"Verification failed: {v.detail}"
        await _save(run, "step.failed", {"step_index": idx})
        return {"run": run, "failure": _fail("verify", v.detail, True)}
    step.status = StepStatus.done
    step.finished_at = now_iso()
    await _save(run, "step.verified", {"step_index": idx})
    return {"run": run, "failure": None}


async def record(state: RunState) -> RunState:
    """Advance the timeline cursor and write the run. Ends the run when no steps remain."""
    d = get_deps()
    run = state["run"]
    run.undo_cursor = sum(1 for s in run.steps if s.status == StepStatus.done)
    run.current_step += 1
    if run.current_step >= len(run.steps):
        run.status = RunStatus.completed
        wf = state["workflow"]
        started = datetime.fromisoformat(run.created_at).timestamp()
        elapsed = int(max(0, time.time() - started))
        run.seconds_saved = max(0, wf.estimated_manual_seconds - min(elapsed, wf.estimated_manual_seconds))
        wf.run_count += 1
        await d.store.save_workflow(wf)
        await _save(run, "run.completed")
    else:
        await _save(run, "run.progress")
    return {"run": run}


async def failure_gate(state: RunState) -> RunState:
    """Pause. Explain in one sentence. Offer retry / skip / stop. Never continue silently."""
    f = state.get("failure")
    run = state["run"]
    assert f
    options = ["retry", "skip", "stop"] if f["retryable"] else ["skip", "stop"]
    if f["node"] in ("plan", "assess_risk") and "skip" in options:
        options.remove("skip")  # nothing sensible to skip to before the first commit
    decision = interrupt(
        {"type": "failure", "run_id": run.id, "node": f["node"], "message": f["message"],
         "step_index": run.current_step, "options": options}
    )
    choice = (decision or {}).get("decision", "stop")
    if choice not in options:
        choice = "stop"
    if choice == "retry":
        run.status = RunStatus.running
        run.pause_reason = None
        await _save(run, "run.resumed")
        return {"run": run, "decision": "retry", "failure": None}
    if choice == "skip":
        step = run.steps[run.current_step]
        step.status = StepStatus.skipped
        step.finished_at = now_iso()
        run.status = RunStatus.running
        run.pause_reason = None
        await _save(run, "step.skipped", {"step_index": run.current_step})
        return {"run": run, "decision": "skip", "failure": None}
    run.status = RunStatus.stopped
    await _save(run, "run.stopped")
    return {"run": run, "decision": "stop", "stopped": True}
