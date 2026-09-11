"""Undo. Reverts committed steps in reverse order through the APIs, verifying each.

The slider position is `run.undo_cursor` = number of committed steps. Moving the
cursor to N reverts steps N.. in reverse. Undo is real: a step is only marked
`reverted` after the integration confirms the record is gone.
"""

from __future__ import annotations

import logging

from ..deps import get_deps
from ..integrations.base import VerifyResult
from ..models import Run, RunStatus, RunStep, StepStatus, now_iso

log = logging.getLogger(__name__)


async def _revert_step(step: RunStep) -> VerifyResult:
    i = get_deps().integrations
    tok = step.undo_token
    if not tok:
        return VerifyResult(False, "No undo token recorded for this step.")
    if tok.kind == "jira_issue":
        return await i.jira.delete_issue(tok.ref["key"])
    if tok.kind == "slack_message":
        return await i.slack.delete_message(tok.ref["channel_id"], tok.ref["ts"])
    if tok.kind == "gmail_label":
        return await i.gmail.remove_label(tok.ref["message_id"], tok.ref["label"])
    return VerifyResult(False, f"Unknown undo token kind {tok.kind}.")


async def _save(run: Run, event: str, extra: dict | None = None) -> None:
    d = get_deps()
    await d.store.save_run(run)
    await d.bus.publish(event, {"run": run.model_dump(mode="json"), **(extra or {})})
    step = extra.get("step_index") if extra else None
    where = f" step={step + 1} {run.steps[step].action}" if isinstance(step, int) else ""
    log.info("%s %s status=%s%s", run.id, event, run.status, where)


def committed_indices(run: Run) -> list[int]:
    return [i for i, s in enumerate(run.steps) if s.status == StepStatus.done]


async def undo_to(run: Run, target_cursor: int) -> Run:
    """Move the slider to `target_cursor` committed steps. Reverts everything above it."""
    committed = committed_indices(run)
    target_cursor = max(0, min(target_cursor, len(committed)))
    to_revert = list(reversed(committed[target_cursor:]))
    if not to_revert:
        return run
    for idx in to_revert:
        step = run.steps[idx]
        step.status = StepStatus.reverting
        await _save(run, "step.reverting", {"step_index": idx})
        try:
            res = await _revert_step(step)
        except Exception as e:
            res = VerifyResult(False, f"Revert call failed ({e}).")
        if res.ok:
            step.status = StepStatus.reverted
            step.reverted_at = now_iso()
            step.verification = {"ok": True, "detail": res.detail, "reverted": True}
            run.undo_cursor = len(committed_indices(run))
            await _save(run, "step.reverted", {"step_index": idx})
        else:
            step.status = StepStatus.revert_failed
            step.error = res.detail
            run.status = RunStatus.paused
            run.pause_reason = f"Undo failed on '{step.title}': {res.detail}"
            await _save(run, "step.revert_failed", {"step_index": idx})
            return run
    remaining = committed_indices(run)
    if not remaining:
        run.status = RunStatus.reverted
    else:
        run.status = RunStatus.partially_reverted
    run.pause_reason = None
    await _save(run, "run.undone")
    return run


async def undo_one(run: Run) -> Run:
    """Ctrl+Z: revert the most recent committed step."""
    return await undo_to(run, len(committed_indices(run)) - 1)
