"""HTTP contract the extension relies on."""

import httpx

from repeat.api.app import create_app
from repeat.seed import seed_demo


async def _client():
    app = create_app()  # lifespan is not run; deps come from the fixture
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_health_reports_sandbox_and_mock(deps):
    async with await _client() as c:
        r = await c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["demo_mode"] is True
    assert body["llm"] == "mock"
    assert body["integrations"] == {"jira": "sandbox", "slack": "sandbox", "gmail": "sandbox"}
    assert all(v["ok"] for v in body["checks"].values())


async def test_latest_run_is_200_when_empty(deps):
    async with await _client() as c:
        r = await c.get("/runs/latest")
    assert r.status_code == 200
    assert r.json() == {"run": None, "interrupt": None, "finished": True}


async def test_full_http_flow_match_decide_undo_reset(deps):
    await seed_demo()
    async with await _client() as c:
        r = await c.post("/runs/match", json={"email_id": "demo-mail-001"})
        assert r.status_code == 200
        state = r.json()
        assert state["interrupt"]["type"] == "approval"
        run_id = state["run"]["id"]

        # matching the same email again returns the same live run, never a duplicate
        r = await c.post("/runs/match", json={"email_id": "demo-mail-001"})
        assert r.json()["run"]["id"] == run_id

        r = await c.post(f"/runs/{run_id}/decide", json={"decision": "all"})
        run = r.json()["run"]
        assert run["status"] == "completed"
        assert [s["status"] for s in run["steps"]] == ["done", "done", "done"]
        assert all(s["undo_token"] for s in run["steps"])

        r = await c.post(f"/runs/{run_id}/undo_one")
        assert r.json()["steps"][2]["status"] == "reverted"
        r = await c.post(f"/runs/{run_id}/undo", json={"cursor": 0})
        assert r.json()["status"] == "reverted"

        r = await c.post("/demo/reset")
        assert r.json()["stats"] == {"demonstrations": 1, "workflows": 1, "runs": 0}


async def test_rename_and_delete_workflow(deps):
    await seed_demo()
    async with await _client() as c:
        wfs = (await c.get("/workflows")).json()
        wid = wfs[0]["id"]
        r = await c.patch(f"/workflows/{wid}", json={"name": "Bugs → Jira + Slack"})
        assert r.json()["name"] == "Bugs → Jira + Slack"
        r = await c.delete(f"/workflows/{wid}")
        assert r.json() == {"ok": True}
        r = await c.post("/runs/match", json={"email_id": "demo-mail-001"})
        assert r.status_code == 404  # nothing learned: the ghost stays silent


async def test_match_lunch_email_reports_no_match(deps):
    await seed_demo()
    async with await _client() as c:
        state = (await c.post("/runs/match", json={"email_id": "demo-mail-003"})).json()
        assert state["run"]["status"] == "no_match"
        assert state["finished"] is True
        assert (await c.get("/runs/latest")).json()["run"] is None
        assert len((await c.get("/runs?include_no_match=true")).json()) == 1


async def test_fault_injection_produces_paused_state(deps):
    await seed_demo()
    async with await _client() as c:
        assert (await c.post("/demo/fault", json={"app": "slack"})).json()["ok"] is True
        state = (await c.post("/runs/match", json={"email_id": "demo-mail-002"})).json()
        state = (await c.post(f"/runs/{state['run']['id']}/decide", json={"decision": "all"})).json()
        assert state["interrupt"]["type"] == "failure"
        assert state["run"]["status"] == "paused"
        assert state["run"]["steps"][1]["status"] == "failed"
        assert "503" in state["run"]["pause_reason"]
