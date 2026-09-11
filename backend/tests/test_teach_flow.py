"""Teach graph: observe -> generalize -> record, including the failure gate."""

from repeat.agent import runner
from repeat.llm.base import LLMError
from repeat.models import Demonstration, EventKind, RecordedEvent
from repeat.seed import demo_demonstration


async def test_teach_learns_workflow_from_demo(deps):
    demo = demo_demonstration("DEMO", "product-updates")
    demo.id = "demo_test_1"
    res = await runner.teach(demo)
    assert res["interrupt"] is None
    wf = res["workflow"]
    assert wf is not None
    assert wf["name"] == "Bug email to Jira and Slack"
    actions = [s["action"] for s in wf["steps"]]
    assert actions == ["jira.create_issue", "slack.post_message", "gmail.apply_label"]
    # subject copied from Gmail became a variable, not a hard-coded value
    assert "{email_subject}" in wf["steps"][0]["fields"]["summary"]
    assert any(v["source"] == "email.sender" for v in wf["variables"])
    saved = await deps.store.get_workflow(wf["id"])
    assert saved is not None and saved.demonstration_id == demo.id


async def test_observe_collapses_repeated_inputs_and_attaches_narration(deps):
    from repeat.agent.nodes import observe

    t0 = 1_000_000.0
    ev = lambda kind, dt, **kw: RecordedEvent(
        kind=kind, ts=t0 + dt, url="u", title="t", app="jira", **kw
    )
    demo = Demonstration(
        events=[
            ev(EventKind.input, 0, field_label="Summary", value="Che"),
            ev(EventKind.input, 300, field_label="Summary", value="Checkout"),
            ev(EventKind.input, 600, field_label="Summary", value="Checkout broken"),
            ev(EventKind.click, 900, target_text="   "),  # empty click is noise
            ev(EventKind.click, 1200, target_text="Create", target_role="button"),
        ],
        narration=[ev(EventKind.narration, 700, transcript="the subject is the summary")],
    )
    out = await observe({"demonstration": demo})
    rows = out["normalized"]
    assert [r["kind"] for r in rows] == ["input", "click"]
    assert rows[0]["value"] == "Checkout broken"
    assert rows[0]["narration"] == ["the subject is the summary"]


async def test_teach_with_no_events_pauses_with_stop_only(deps):
    demo = Demonstration(id="demo_empty", events=[], narration=[])
    res = await runner.teach(demo)
    assert res["workflow"] is None
    assert res["interrupt"]["type"] == "failure"
    assert res["interrupt"]["options"] == ["stop"]
    res = await runner.resume_teach(demo.id, "stop")
    assert res["stopped"] is True


async def test_teach_llm_failure_offers_retry_then_succeeds(deps, monkeypatch):
    calls = {"n": 0}
    real = deps.llm.complete_structured

    async def flaky(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise LLMError("simulated outage")
        return await real(**kw)

    monkeypatch.setattr(deps.llm, "complete_structured", flaky)
    demo = demo_demonstration("DEMO", "product-updates")
    demo.id = "demo_flaky"
    res = await runner.teach(demo)
    assert res["interrupt"]["type"] == "failure"
    assert "retry" in res["interrupt"]["options"]
    assert "simulated outage" in res["interrupt"]["message"]
    res = await runner.resume_teach(demo.id, "retry")
    assert res["interrupt"] is None
    assert res["workflow"]["name"]
