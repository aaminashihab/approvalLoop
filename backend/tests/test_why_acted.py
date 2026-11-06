"""Regression test: GET /api/actions/{id}/why-acted used to raise NameError (500) for every real action."""
from fastapi.testclient import TestClient
from approval_loop.api.app import app

client = TestClient(app)
HEADERS = {"X-API-Key": "dev-scheduler-secret-key"}


def test_why_acted_explains_a_real_reminder_action():
    client.post("/api/seed")
    client.post("/api/demo/advance-time", json={"seconds": 3600})
    tick = client.post("/api/tick", headers=HEADERS)
    assert tick.status_code == 200
    actions = tick.json()["actions"]
    assert actions, "the seeded reports should produce at least one reminder"

    action_id = actions[0]["action_id"]
    res = client.get(f"/api/actions/{action_id}/why-acted")
    assert res.status_code == 200
    body = res.json()
    assert body["action_id"] == action_id
    assert isinstance(body["breakdown"]["is_race_condition_prevented"], bool)


def test_why_acted_unknown_action_is_404():
    assert client.get("/api/actions/does-not-exist/why-acted").status_code == 404
