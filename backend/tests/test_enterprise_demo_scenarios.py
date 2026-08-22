import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from approval_loop.api.app import app
from approval_loop.domain.gateway_models import GatewayDecisionEnum

client = TestClient(app)

def test_critical_demo_scenario_a_automatic_allow():
    """
    Case A: Finance Agent requests Refund of ₹2,000.
    Expected: ALLOW -> automatic execution.
    """
    response = client.post("/api/demo/scenario-a")
    assert response.status_code == 200
    data = response.json()
    assert data["decision"]["decision"] == GatewayDecisionEnum.ALLOW.value
    assert data["decision"]["requires_human_approval"] is False
    assert "Automatic execution permitted" in data["decision"]["reason"]

def test_critical_demo_scenario_b_human_approval_flow():
    """
    Case B: Finance Agent requests Refund of ₹20,000.
    Expected: REQUIRE_HUMAN_APPROVAL -> pauses workflow -> human approves -> completes.
    """
    response = client.post("/api/demo/scenario-b")
    assert response.status_code == 200
    data = response.json()
    assert data["decision"]["decision"] == GatewayDecisionEnum.REQUIRE_HUMAN_APPROVAL.value
    assert data["decision"]["requires_human_approval"] is True
    action_id = data["decision"]["action_record_id"]
    
    headers = {"X-API-Key": "dev-scheduler-secret-key"}
    # Check pending actions endpoint
    pending_res = client.get("/api/gateway/actions/pending", headers=headers)
    assert pending_res.status_code == 200
    pending_items = pending_res.json()
    assert any(item["action_id"] == action_id for item in pending_items)
    
    # Human Operator Approves via API
    approve_res = client.post(
        f"/api/gateway/actions/{action_id}/approve",
        json={"operator": "Chief Risk Officer", "notes": "Approved for enterprise partner"},
        headers=headers
    )
    assert approve_res.status_code == 200
    app_data = approve_res.json()
    assert app_data["decision"]["decision"] == GatewayDecisionEnum.ALLOW.value
    assert "Human Approval Granted" in app_data["decision"]["reason"]

def test_critical_demo_scenario_c_deterministic_denial():
    """
    Case C: Finance Agent requests Refund of ₹100,000.
    Expected: DENY -> Even if Gemini proposes it, deterministic policy strictly rejects it.
    """
    response = client.post("/api/demo/scenario-c")
    assert response.status_code == 200
    data = response.json()
    assert data["decision"]["decision"] == GatewayDecisionEnum.DENY.value
    assert data["decision"]["requires_human_approval"] is False
    assert "exceeds corporate authorization ceiling" in data["decision"]["reason"]
