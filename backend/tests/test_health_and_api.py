import pytest
from fastapi.testclient import TestClient
from approval_loop.api.app import app

client = TestClient(app)

def test_health_live_endpoint():
    res = client.get("/health/live")
    assert res.status_code == 200
    assert res.json()["status"] == "alive"

def test_health_ready_endpoint():
    res = client.get("/health/ready")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert data["agents_registered"] >= 3
    assert data["gateway"] == "active"

def test_healthz_backward_compatibility():
    res = client.get("/healthz")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "Google GenAI SDK" in data["framework"]

def test_agent_registry_endpoints():
    res = client.get("/api/registry/agents")
    assert res.status_code == 200
    agents = res.json()
    assert len(agents) >= 3
    
    agent_res = client.get("/api/registry/agents/finance-agent")
    assert agent_res.status_code == 200
    assert agent_res.json()["agent_id"] == "finance-agent"

def test_memory_bank_endpoints():
    res = client.get("/api/memory/workflows")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
