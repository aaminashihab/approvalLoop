import time
import pytest
from decimal import Decimal
from approval_loop.domain.agent_registry import AgentRegistryService, AgentStatus
from approval_loop.domain.gateway_models import AgentActionProposal, AgentAuthContext
from approval_loop.identity.auth_provider import AgentIdentityProvider

@pytest.fixture
def setup_identity():
    registry = AgentRegistryService()
    id_provider = AgentIdentityProvider(registry_service=registry, secret_key="test-secret-key-12345", token_max_age_seconds=10)
    return registry, id_provider

def test_valid_agent_identity_verification(setup_identity):
    registry, id_provider = setup_identity
    token = id_provider.generate_agent_token("finance-agent", "1.2.0")
    
    proposal = AgentActionProposal(
        agent_id="finance-agent",
        agent_version="1.2.0",
        action_name="issue_refund",
        target_resource_id="REF-100",
        amount=Decimal("1500.00"),
        recipient="customer@company.com"
    )
    auth_ctx = AgentAuthContext(
        agent_id="finance-agent",
        agent_version="1.2.0",
        token=token
    )
    
    ok, reason, claims = id_provider.verify_agent_request(proposal, auth_ctx)
    assert ok is True
    assert "authenticated successfully" in reason
    assert auth_ctx.verified is True
    assert auth_ctx.verification_method == "HMAC-SHA256"

def test_tampered_token_rejection(setup_identity):
    registry, id_provider = setup_identity
    token = id_provider.generate_agent_token("finance-agent", "1.2.0")
    # Tamper with signature
    tampered_token = token[:-4] + "ffff"
    
    proposal = AgentActionProposal(
        agent_id="finance-agent",
        agent_version="1.2.0",
        action_name="issue_refund",
        target_resource_id="REF-100",
        amount=Decimal("1500.00"),
        recipient="customer@company.com"
    )
    auth_ctx = AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0", token=tampered_token)
    
    ok, reason, _ = id_provider.verify_agent_request(proposal, auth_ctx)
    assert ok is False
    assert "signature verification failed" in reason

def test_unregistered_agent_rejection(setup_identity):
    registry, id_provider = setup_identity
    token = id_provider.generate_agent_token("rogue-agent", "1.0.0")
    
    proposal = AgentActionProposal(
        agent_id="rogue-agent",
        agent_version="1.0.0",
        action_name="issue_refund",
        target_resource_id="REF-100",
        amount=Decimal("1500.00"),
        recipient="customer@company.com"
    )
    auth_ctx = AgentAuthContext(agent_id="rogue-agent", agent_version="1.0.0", token=token)
    
    ok, reason, _ = id_provider.verify_agent_request(proposal, auth_ctx)
    assert ok is False
    assert "not registered" in reason

def test_disabled_agent_rejection(setup_identity):
    registry, id_provider = setup_identity
    registry.update_agent_status("finance-agent", AgentStatus.DISABLED)
    token = id_provider.generate_agent_token("finance-agent", "1.2.0")
    
    proposal = AgentActionProposal(
        agent_id="finance-agent",
        agent_version="1.2.0",
        action_name="issue_refund",
        target_resource_id="REF-100",
        amount=Decimal("1500.00"),
        recipient="customer@company.com"
    )
    auth_ctx = AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0", token=token)
    
    ok, reason, _ = id_provider.verify_agent_request(proposal, auth_ctx)
    assert ok is False
    assert "status is 'disabled'" in reason

def test_unauthorized_action_capability_rejection(setup_identity):
    registry, id_provider = setup_identity
    token = id_provider.generate_agent_token("support-agent", "1.1.0")
    
    # Support agent trying to issue an unapproved high-risk financial refund instead of a support credit
    proposal = AgentActionProposal(
        agent_id="support-agent",
        agent_version="1.1.0",
        action_name="unauthorized_wire_transfer",
        target_resource_id="ACC-999",
        amount=Decimal("50000.00"),
        recipient="hacker@external.com"
    )
    auth_ctx = AgentAuthContext(agent_id="support-agent", agent_version="1.1.0", token=token)
    
    ok, reason, _ = id_provider.verify_agent_request(proposal, auth_ctx)
    assert ok is False
    assert "Action Permission Denied" in reason
