"""End-to-end: seed -> match -> plan -> risk -> approval -> step commits -> undo."""

from repeat.agent import runner, undo
from repeat.integrations.sandbox import DEMO_EMAILS, SandboxJira
from repeat.models import Run, RunStatus, StepStatus
from repeat.seed import DEMO_WORKFLOW_ID, seed_demo


async def _seeded(deps):
    await seed_demo()
    wf = await deps.store.get_workflow(DEMO_WORKFLOW_ID)
    assert wf is not None
    return wf


async def test_full_run_step_mode_then_undo(deps):
    wf = await _seeded(deps)
    email = DEMO_EMAILS[0]

    res = await runner.start_run(wf, email)
    assert res["interrupt"]["type"] == "approval"
    assert res["run"]["status"] == "awaiting_approval"
    risk = res["run"]["risk"]
    assert risk["records_created"] == 1 and risk["external_messages"] == 1
    assert "Jira" in risk["blast_radius"]
    run_id = res["run"]["id"]

    # Tab: approve in step mode -> step 1 is previewed (ghost fill) before it commits
    res = await runner.resume_run(run_id, "step")
    assert res["interrupt"]["type"] == "step_gate"
    assert res["interrupt"]["step_index"] == 0
    run = Run.model_validate(res["run"])
    assert run.steps[0].status == StepStatus.previewing
    assert run.steps[0].inputs["summary"] == email.subject

    # Tab again: commit step 1, park at step 2 preview
    res = await runner.resume_run(run_id, "commit")
    assert res["interrupt"]["type"] == "step_gate"
    assert res["interrupt"]["step_index"] == 1
    run = Run.model_validate(res["run"])
    assert run.steps[0].status == StepStatus.done
    assert run.steps[0].outputs["issue_key"].startswith("DEMO-")
    assert run.steps[0].verification["ok"] is True
    assert run.steps[1].status == StepStatus.previewing
    # the Slack draft contains the real ticket key from step 1
    key = run.steps[0].outputs["issue_key"]

    res = await runner.resume_run(run_id, "commit")
    run = Run.model_validate(res["run"])
    assert key in run.steps[1].inputs["text"]
    assert run.steps[1].status == StepStatus.done
    assert res["interrupt"]["type"] == "step_gate"

    res = await runner.resume_run(run_id, "commit")
    run = Run.model_validate(res["run"])
    assert run.status == RunStatus.completed
    assert res["interrupt"] is None
    assert run.undo_cursor == 3
    assert run.seconds_saved > 0

    # undo everything, in reverse, with verification
    run = await undo.undo_to(run, 0)
    assert run.status == RunStatus.reverted
    assert all(s.status == StepStatus.reverted for s in run.steps)
    jira: SandboxJira = deps.integrations.jira  # type: ignore[assignment]
    assert key not in jira.issues
    assert not deps.integrations.slack.messages


async def test_run_all_mode(deps):
    wf = await _seeded(deps)
    res = await runner.start_run(wf, DEMO_EMAILS[1])
    res = await runner.resume_run(res["run"]["id"], "all")
    assert res["interrupt"] is None
    assert res["run"]["status"] == "completed"


async def test_no_match_for_lunch_email(deps):
    wf = await _seeded(deps)
    res = await runner.start_run(wf, DEMO_EMAILS[2])
    assert res["interrupt"] is None
    assert res["run"]["status"] == "stopped"
    assert res["run"]["match_confidence"] < 0.6


async def test_failure_pauses_then_retry_succeeds(deps):
    wf = await _seeded(deps)
    jira: SandboxJira = deps.integrations.jira  # type: ignore[assignment]
    jira.fail_next = "Jira returned 503 while creating the issue."
    res = await runner.start_run(wf, DEMO_EMAILS[0])
    res = await runner.resume_run(res["run"]["id"], "step")
    assert res["interrupt"]["type"] == "step_gate"
    res = await runner.resume_run(res["run"]["id"], "commit")
    assert res["interrupt"]["type"] == "failure"
    assert res["interrupt"]["options"] == ["retry", "skip", "stop"]
    assert res["run"]["status"] == "paused"
    assert "503" in res["run"]["pause_reason"]
    res = await runner.resume_run(res["run"]["id"], "retry")
    assert res["interrupt"]["type"] == "step_gate"
    assert res["run"]["steps"][0]["status"] == "done"
    assert res["run"]["steps"][0]["attempts"] == 2


async def test_failure_skip_continues(deps):
    wf = await _seeded(deps)
    deps.integrations.slack.fail_next = "Slack error: channel_not_found."
    res = await runner.start_run(wf, DEMO_EMAILS[0])
    res = await runner.resume_run(res["run"]["id"], "all")
    assert res["interrupt"]["type"] == "failure"
    res = await runner.resume_run(res["run"]["id"], "skip")
    run = Run.model_validate(res["run"])
    assert run.steps[1].status == StepStatus.skipped
    assert run.steps[2].status == StepStatus.done
    assert run.status == RunStatus.completed


async def test_undo_one_steps_back_single(deps):
    wf = await _seeded(deps)
    res = await runner.start_run(wf, DEMO_EMAILS[0])
    res = await runner.resume_run(res["run"]["id"], "all")
    run = Run.model_validate(res["run"])
    run = await undo.undo_one(run)
    assert run.steps[2].status == StepStatus.reverted
    assert run.steps[1].status == StepStatus.done
    assert run.status == RunStatus.partially_reverted
    assert run.undo_cursor == 2
