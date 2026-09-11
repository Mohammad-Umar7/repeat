"""Graph topology. Two StateGraphs share one MemorySaver so interrupts can be resumed
by thread id (demonstration id for teach, run id for runs)."""

from __future__ import annotations

from functools import lru_cache

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from . import nodes
from .state import RunState, TeachState


@lru_cache
def checkpointer() -> MemorySaver:
    return MemorySaver()


# ── Teach ──────────────────────────────────────────────────────────────


def _teach_after(node: str):
    def route(state: TeachState) -> str:
        if state.get("stopped"):
            return END
        return "failure_gate" if state.get("failure") else node

    return route


def _teach_after_gate(state: TeachState) -> str:
    if state.get("stopped"):
        return END
    return state.get("failure_origin", "generalize")  # type: ignore[return-value]


@lru_cache
def teach_graph():
    g: StateGraph = StateGraph(TeachState)
    g.add_node("observe", nodes.observe)
    g.add_node("generalize", nodes.generalize)
    g.add_node("record", nodes.record_workflow)
    g.add_node("failure_gate", _teach_gate_with_origin)
    g.add_edge(START, "observe")
    g.add_conditional_edges("observe", _teach_after("generalize"), ["generalize", "failure_gate", END])
    g.add_conditional_edges("generalize", _teach_after("record"), ["record", "failure_gate", END])
    g.add_conditional_edges("record", _teach_after(END), ["failure_gate", END])
    g.add_conditional_edges(
        "failure_gate", _teach_after_gate, ["observe", "generalize", "record", END]
    )
    return g.compile(checkpointer=checkpointer())


async def _teach_gate_with_origin(state: TeachState) -> TeachState:
    f = state.get("failure")
    out = await nodes.teach_failure_gate(state)
    if f and out.get("decision") == "retry":
        out["failure_origin"] = f["node"]  # type: ignore[typeddict-unknown-key]
    return out


# ── Run ────────────────────────────────────────────────────────────────


def _after_match(state: RunState) -> str:
    return "plan" if state.get("matched") else END


def _after(node_ok: str):
    def route(state: RunState) -> str:
        if state.get("stopped"):
            return END
        return "failure_gate" if state.get("failure") else node_ok

    return route


def _after_approval(state: RunState) -> str:
    """Step mode previews every step, including the first, before it commits."""
    if state.get("stopped"):
        return END
    return "step_gate" if state.get("mode") == "step" else "execute"


def _after_step_gate(state: RunState) -> str:
    return END if state.get("stopped") else "execute"


def _after_record(state: RunState) -> str:
    run = state["run"]
    if run.current_step >= len(run.steps):
        return END
    return "step_gate" if state.get("mode") == "step" else "execute"


def _after_gate(state: RunState) -> str:
    if state.get("stopped"):
        return END
    f_origin = state.get("failure_origin", "execute")
    decision = state.get("decision")
    if decision == "retry":
        return f_origin  # type: ignore[return-value]
    if decision == "skip":
        return "record"
    return END


async def _gate_with_origin(state: RunState) -> RunState:
    f = state.get("failure")
    out = await nodes.failure_gate(state)
    if f:
        out["failure_origin"] = f["node"]  # type: ignore[typeddict-unknown-key]
    return out


@lru_cache
def run_graph():
    g: StateGraph = StateGraph(RunState)
    g.add_node("match", nodes.match)
    g.add_node("plan", nodes.plan)
    g.add_node("assess_risk", nodes.assess_risk)
    g.add_node("await_approval", nodes.await_approval)
    g.add_node("step_gate", nodes.step_gate)
    g.add_node("execute", nodes.execute)
    g.add_node("verify", nodes.verify)
    g.add_node("record", nodes.record)
    g.add_node("failure_gate", _gate_with_origin)

    g.add_edge(START, "match")
    g.add_conditional_edges("match", _after_match, ["plan", END])
    g.add_conditional_edges("plan", _after("assess_risk"), ["assess_risk", "failure_gate", END])
    g.add_conditional_edges(
        "assess_risk", _after("await_approval"), ["await_approval", "failure_gate", END]
    )
    g.add_conditional_edges("await_approval", _after_approval, ["step_gate", "execute", END])
    g.add_conditional_edges("step_gate", _after_step_gate, ["execute", END])
    g.add_conditional_edges("execute", _after("verify"), ["verify", "failure_gate", END])
    g.add_conditional_edges("verify", _after("record"), ["record", "failure_gate", END])
    g.add_conditional_edges("record", _after_record, ["step_gate", "execute", END])
    g.add_conditional_edges(
        "failure_gate", _after_gate, ["plan", "assess_risk", "execute", "verify", "record", END]
    )
    return g.compile(checkpointer=checkpointer())
