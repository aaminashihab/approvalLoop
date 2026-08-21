import pytest
from approval_loop.domain.agent_registry import AgentRegistryService, AgentRegistration, AgentStatus, RiskLevel
from approval_loop.storage.memory_repo import InMemoryRepository

def test_default_fleet_initialized():
    repo = InMemoryRepository()
    service = AgentRegistryService(repo=repo)
    agents = service.list_agents()
    assert len(agents) >= 3
    
    agent_ids = [a.agent_id for a in agents]
    assert "finance-agent" in agent_ids
    assert "support-agent" in agent_ids
    assert "sales-agent" in agent_ids

def test_register_and_retrieve_agent():
    service = AgentRegistryService()
    custom_agent = AgentRegistration(
        agent_id="hr-compliance-agent",
        name="HR Compliance & Offer Agent",
        description="Evaluates job offers and equity allocations.",
        owner="hr-ops@company.internal",
        version="1.0.0",
        status=AgentStatus.ACTIVE,
        capabilities=["offer_review", "equity_granting"],
        allowed_tools=["workday_api", "notification_worker"],
        allowed_actions=["issue_offer_letter", "grant_equity"],
        policy_profile="hr-v1",
        risk_level=RiskLevel.HIGH
    )
    service.register_agent(custom_agent)
    
    retrieved = service.get_agent("hr-compliance-agent")
    assert retrieved is not None
    assert retrieved.name == "HR Compliance & Offer Agent"
    assert retrieved.status == AgentStatus.ACTIVE
    assert service.is_action_allowed("hr-compliance-agent", "grant_equity") is True
    assert service.is_action_allowed("hr-compliance-agent", "unauthorized_wire_transfer") is False

def test_disable_agent_and_permission_check():
    service = AgentRegistryService()
    finance = service.get_agent("finance-agent")
    assert finance is not None
    assert service.is_action_allowed("finance-agent", "issue_refund") is True
    
    # Disable agent
    service.update_agent_status("finance-agent", AgentStatus.DISABLED)
    assert service.get_agent("finance-agent").status == AgentStatus.DISABLED
    assert service.is_action_allowed("finance-agent", "issue_refund") is False
