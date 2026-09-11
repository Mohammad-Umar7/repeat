"""HTTP routes. Thin: validate, call the agent runner or store, return JSON."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import __version__
from ..agent import runner, undo
from ..deps import get_deps
from ..integrations import integration_modes
from ..llm.base import LLMError
from ..models import Demonstration, EmailContext, RecordedEvent
from ..seed import seed_demo

router = APIRouter()


# ── health ─────────────────────────────────────────────────────────────


@router.get("/health")
async def health():
    d = get_deps()
    checks = {}
    for name, client in (("jira", d.integrations.jira), ("slack", d.integrations.slack), ("gmail", d.integrations.gmail)):
        ok, detail = await client.health()
        checks[name] = {"ok": ok, "detail": detail}
    return {
        "ok": True,
        "version": __version__,
        "demo_mode": d.settings.repeat_demo_mode,
        "llm": d.llm.name,
        "integrations": integration_modes(d.integrations),
        "checks": checks,
        "narration_enabled": d.settings.repeat_narration_enabled and d.llm.name == "openai",
        "slack_channel": d.settings.slack_channel,
        "jira_project": d.settings.jira_project_key,
        "store": await d.store.stats(),
    }


# ── workflows ──────────────────────────────────────────────────────────


class RenameBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.get("/workflows")
async def list_workflows():
    return [w.model_dump(mode="json") for w in await get_deps().store.list_workflows()]


@router.get("/workflows/{wf_id}")
async def get_workflow(wf_id: str):
    wf = await get_deps().store.get_workflow(wf_id)
    if not wf:
        raise HTTPException(404, "workflow not found")
    return wf.model_dump(mode="json")


@router.patch("/workflows/{wf_id}")
async def rename_workflow(wf_id: str, body: RenameBody):
    d = get_deps()
    wf = await d.store.get_workflow(wf_id)
    if not wf:
        raise HTTPException(404, "workflow not found")
    wf.name = body.name.strip()
    await d.store.save_workflow(wf)
    await d.bus.publish("workflow.updated", {"workflow": wf.model_dump(mode="json")})
    return wf.model_dump(mode="json")


@router.delete("/workflows/{wf_id}")
async def delete_workflow(wf_id: str):
    d = get_deps()
    if not await d.store.delete_workflow(wf_id):
        raise HTTPException(404, "workflow not found")
    await d.bus.publish("workflow.deleted", {"workflow_id": wf_id})
    return {"ok": True}


# ── teach ──────────────────────────────────────────────────────────────


class DemonstrationBody(BaseModel):
    events: list[RecordedEvent]
    narration: list[RecordedEvent] = Field(default_factory=list)


@router.post("/demonstrations")
async def create_demonstration(body: DemonstrationBody):
    d = get_deps()
    demo = Demonstration(events=body.events, narration=body.narration)
    await d.store.save_demonstration(demo)
    result = await runner.teach(demo)
    return {"demonstration_id": demo.id, **result}


class DecisionBody(BaseModel):
    decision: str


@router.post("/demonstrations/{demo_id}/decide")
async def decide_demonstration(demo_id: str, body: DecisionBody):
    if body.decision not in ("retry", "stop"):
        raise HTTPException(400, "decision must be retry or stop")
    return {"demonstration_id": demo_id, **await runner.resume_teach(demo_id, body.decision)}


@router.post("/narration/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    d = get_deps()
    if not (d.settings.repeat_narration_enabled and d.llm.name == "openai"):
        raise HTTPException(409, "narration is disabled: set OPENAI_API_KEY to enable transcription")
    data = await audio.read()
    if len(data) < 1024:
        return {"text": ""}
    try:
        text = await d.llm.transcribe(data, audio.filename or "narration.webm")
    except LLMError as e:
        raise HTTPException(502, str(e)) from e
    return {"text": text}


# ── inbox ──────────────────────────────────────────────────────────────


@router.get("/inbox/latest")
async def inbox_latest():
    email = await get_deps().integrations.gmail.latest_email()
    if not email:
        raise HTTPException(404, "inbox is empty")
    return email.model_dump(mode="json")


@router.get("/inbox/{message_id}")
async def inbox_get(message_id: str):
    email = await get_deps().integrations.gmail.get_email(message_id)
    if not email:
        raise HTTPException(404, "email not found")
    return email.model_dump(mode="json")


# ── runs ───────────────────────────────────────────────────────────────


class MatchBody(BaseModel):
    """Either an email id (fetched through Gmail) or a full email captured from the page."""

    email_id: str | None = None
    email: EmailContext | None = None
    workflow_id: str | None = None


@router.post("/runs/match")
async def match_email(body: MatchBody):
    d = get_deps()
    email = body.email
    if email is None and body.email_id:
        email = await d.integrations.gmail.get_email(body.email_id)
    if email is None:
        raise HTTPException(400, "provide email or email_id")
    existing = await d.store.find_run_for_email(email.id)
    if existing and existing.status.value not in ("completed", "reverted", "partially_reverted"):
        return await runner.run_state(existing.id)
    workflows = await d.store.list_workflows()
    if body.workflow_id:
        workflows = [w for w in workflows if w.id == body.workflow_id]
    if not workflows:
        raise HTTPException(404, "no workflows learned yet")
    best = None
    for wf in workflows:
        res = await runner.start_run(wf, email)
        run = res["run"] or {}
        if run.get("status") != "stopped":
            return res
        if best is None or run.get("match_confidence", 0) > best["run"].get("match_confidence", 0):
            best = res
    return best


@router.get("/runs")
async def list_runs(limit: int = 20):
    return [r.model_dump(mode="json") for r in await get_deps().store.list_runs(limit)]


@router.get("/runs/latest")
async def latest_run():
    """200 with a null run when there is none: the panel polls this on open and a 404
    would show up as a console error, which the demo path must never produce."""
    run = await get_deps().store.latest_run()
    if not run:
        return {"run": None, "interrupt": None, "finished": True}
    return await runner.run_state(run.id)


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    if not await get_deps().store.get_run(run_id):
        raise HTTPException(404, "run not found")
    return await runner.run_state(run_id)


class RunDecision(BaseModel):
    decision: Literal["step", "all", "dismiss", "commit", "retry", "skip", "stop"]


@router.post("/runs/{run_id}/decide")
async def decide_run(run_id: str, body: RunDecision):
    if not await get_deps().store.get_run(run_id):
        raise HTTPException(404, "run not found")
    return await runner.resume_run(run_id, body.decision)


class UndoBody(BaseModel):
    cursor: int = Field(ge=0)


@router.post("/runs/{run_id}/undo")
async def undo_run(run_id: str, body: UndoBody):
    run = await get_deps().store.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    run = await undo.undo_to(run, body.cursor)
    return run.model_dump(mode="json")


@router.post("/runs/{run_id}/undo_one")
async def undo_one(run_id: str):
    run = await get_deps().store.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    run = await undo.undo_one(run)
    return run.model_dump(mode="json")


# ── demo ───────────────────────────────────────────────────────────────


@router.post("/demo/reset")
async def demo_reset():
    return await seed_demo(wipe=True)


class FaultBody(BaseModel):
    app: Literal["jira", "slack"]
    message: str = "The service returned 503 Service Unavailable."


@router.post("/demo/fault")
async def demo_fault(body: FaultBody):
    """Arm a one-shot failure in the sandbox so the paused state can be shown on stage."""
    d = get_deps()
    client = getattr(d.integrations, body.app)
    if not hasattr(client, "fail_next"):
        raise HTTPException(409, f"{body.app} is live, not sandboxed; faults cannot be injected")
    client.fail_next = body.message
    return {"ok": True, "armed": body.app}
