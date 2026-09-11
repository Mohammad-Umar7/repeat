"""Drives the graphs. The HTTP layer only ever calls these three functions.

Each call returns the pending interrupt (if any) so the caller knows whether the
graph is waiting on the human, and for what.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.types import Command

from ..deps import get_deps
from ..models import Demonstration, EmailContext, Run, RunStatus, Workflow
from .graph import run_graph, teach_graph

log = logging.getLogger(__name__)


def _pending_interrupt(snapshot) -> dict[str, Any] | None:
    for task in getattr(snapshot, "tasks", ()):
        for intr in getattr(task, "interrupts", ()):
            return dict(intr.value)
    return None


# ── Teach ──────────────────────────────────────────────────────────────


async def teach(demo: Demonstration) -> dict[str, Any]:
    cfg = {"configurable": {"thread_id": f"teach:{demo.id}"}}
    g = teach_graph()
    await g.ainvoke({"demonstration": demo, "failure": None, "stopped": False}, cfg)
    return _teach_result(await g.aget_state(cfg))


async def resume_teach(demo_id: str, decision: str) -> dict[str, Any]:
    cfg = {"configurable": {"thread_id": f"teach:{demo_id}"}}
    g = teach_graph()
    await g.ainvoke(Command(resume={"decision": decision}), cfg)
    return _teach_result(await g.aget_state(cfg))


def _teach_result(snap) -> dict[str, Any]:
    values = snap.values or {}
    wf: Workflow | None = values.get("workflow") if not values.get("failure") else None
    return {
        "workflow": wf.model_dump(mode="json") if wf and not values.get("stopped") and not _pending_interrupt(snap) else None,
        "interrupt": _pending_interrupt(snap),
        "stopped": bool(values.get("stopped")),
    }


# ── Run ────────────────────────────────────────────────────────────────


async def start_run(workflow: Workflow, email: EmailContext) -> dict[str, Any]:
    """Match + plan + risk, then park at the approval interrupt (or END on no-match)."""
    d = get_deps()
    run = Run(workflow_id=workflow.id, workflow_name=workflow.name, email=email)
    await d.store.save_run(run)
    cfg = {"configurable": {"thread_id": run.id}}
    g = run_graph()
    await g.ainvoke(
        {"workflow": workflow, "email": email, "run": run, "mode": "step", "failure": None, "stopped": False},
        cfg,
    )
    return await _run_result(run.id)


async def resume_run(run_id: str, decision: str) -> dict[str, Any]:
    cfg = {"configurable": {"thread_id": run_id}}
    g = run_graph()
    snap = await g.aget_state(cfg)
    if not _pending_interrupt(snap):
        return await _run_result(run_id)
    await g.ainvoke(Command(resume={"decision": decision}), cfg)
    return await _run_result(run_id)


async def run_state(run_id: str) -> dict[str, Any]:
    return await _run_result(run_id)


async def _run_result(run_id: str) -> dict[str, Any]:
    d = get_deps()
    cfg = {"configurable": {"thread_id": run_id}}
    snap = await run_graph().aget_state(cfg)
    run = await d.store.get_run(run_id)
    if run is None and snap.values:
        run = snap.values.get("run")
    return {
        "run": run.model_dump(mode="json") if run else None,
        "interrupt": _pending_interrupt(snap),
        "finished": bool(run and run.status in (RunStatus.completed, RunStatus.stopped, RunStatus.failed)),
    }
