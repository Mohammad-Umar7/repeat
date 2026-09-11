"""Small units the demo leans on: templating, mock matching/risk, orphan cleanup."""

from repeat.agent.nodes import fill_template
from repeat.agent.schemas import MatchOutput, RiskOutput
from repeat.integrations.sandbox import DEMO_EMAILS
from repeat.llm.mock_provider import MockProvider
from repeat.models import Run, RunStatus, RunStep, StepAction, StepStatus
from repeat.prompts import render
from repeat.seed import demo_workflow


def test_fill_template_leaves_unknown_placeholders_intact():
    out = fill_template("New bug: *{email_subject}* → {issue_key}", {"email_subject": "Blank page"})
    assert out == "New bug: *Blank page* → {issue_key}"


def test_fill_template_ignores_non_identifier_braces():
    assert fill_template('json {"a": 1} and {1}', {}) == 'json {"a": 1} and {1}'


async def test_mock_match_scores_bug_reports_above_threshold():
    wf = demo_workflow("DEMO", "product-updates")
    llm = MockProvider()
    scores = {}
    for email in DEMO_EMAILS:
        system, user = render(
            "match", {"trigger": wf.trigger.model_dump(), "email": email.model_dump()}
        )
        m = await llm.complete_structured(system=system, user=user, schema=MatchOutput)
        scores[email.id] = (m.matches, m.confidence)
    assert scores["demo-mail-001"][0] and scores["demo-mail-002"][0]
    assert not scores["demo-mail-003"][0]
    assert (
        scores["demo-mail-003"][1]
        < 0.6
        <= min(scores["demo-mail-001"][1], scores["demo-mail-002"][1])
    )


async def test_mock_risk_counts_and_blast_radius_line():
    llm = MockProvider()
    steps = [
        {"action": "jira.create_issue", "app": "jira", "inputs": {}},
        {"action": "slack.post_message", "app": "slack", "inputs": {}},
        {"action": "gmail.apply_label", "app": "gmail", "inputs": {}},
    ]
    system, user = render("assess_risk", {"steps": steps, "slack_channel": "product-updates"})
    r = await llm.complete_structured(system=system, user=user, schema=RiskOutput)
    assert (r.records_created, r.external_messages, r.records_modified, r.records_deleted) == (
        1,
        1,
        1,
        0,
    )
    assert r.level == "low"
    assert r.blast_radius.startswith("Creates 1 Jira issue, posts 1 message to #product-updates")
    assert r.blast_radius.endswith("no external emails, no payments.")


async def test_stop_orphaned_runs_keeps_committed_steps_undoable(deps):
    run = Run(
        workflow_id="wf",
        workflow_name="wf",
        email=DEMO_EMAILS[0],
        status=RunStatus.running,
        steps=[
            RunStep(
                id="a",
                workflow_step_id="s1",
                action=StepAction.jira_create_issue,
                app="jira",
                title="x",
                status=StepStatus.done,
            ),
            RunStep(
                id="b",
                workflow_step_id="s2",
                action=StepAction.slack_post_message,
                app="slack",
                title="y",
                status=StepStatus.previewing,
            ),
        ],
    )
    await deps.store.save_run(run)
    n = await deps.store.stop_orphaned_runs("restarted")
    assert n == 1
    saved = await deps.store.get_run(run.id)
    assert saved is not None
    assert saved.status == RunStatus.stopped and saved.pause_reason == "restarted"
    assert saved.steps[0].status == StepStatus.done  # still reversible
    assert saved.steps[1].status == StepStatus.planned  # preview cleared


def test_prompt_registry_embeds_data_block():
    system, user = render("plan", {"x": 1})
    assert "plan node" in system
    assert user.rstrip().endswith('"x": 1\n}')
