import pytest
from decimal import Decimal
from approval_loop.domain.agent_registry import AgentRegistryService
from approval_loop.domain.gateway_models import (
    AgentActionProposal, AgentAuthContext, GatewayDecisionEnum
)
from approval_loop.identity.auth_provider import AgentIdentityProvider
from approval_loop.guardrails.safety_guardrail import ModelSafetyGuardrail
from approval_loop.policy.policy_engine import PolicyEngine
from approval_loop.memory.memory_bank import MemoryBankService, WorkflowState
from approval_loop.worker.worker import MockNotificationProvider
from approval_loop.gateway.gateway import AgentGateway

@pytest.fixture
def setup_gateway():
    registry = AgentRegistryService()
    id_provider = AgentIdentityProvider(registry_service=registry, secret_key="gw-test-secret")
    guardrail = ModelSafetyGuardrail()
    policy = PolicyEngine()
    memory_bank = MemoryBankService()
    worker = MockNotificationProvider()
    
    gateway = AgentGateway(
        registry=registry,
        identity_provider=id_provider,
        policy_engine=policy,
        memory_bank=memory_bank,
        worker=worker,
        guardrail=guardrail
    )
    return gateway, id_provider, worker, memory_bank

def test_gateway_allow_low_risk_action(setup_gateway):
    gateway, id_provider, worker, memory_bank = setup_gateway
    token = id_provider.generate_agent_token("finance-agent", "1.2.0")
    
    proposal = AgentActionProposal(
        agent_id="finance-agent",
        agent_version="1.2.0",
        action_name="issue_refund",
        target_resource_id="REF-101",
        amount=Decimal("1500.00"),
        currency="INR",
        recipient="customer@company.com",
        justification="Customer requested return for damaged shipment"
    )
    auth_ctx = AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0", token=token)
    
    decision = gateway.authorize_action(proposal, auth_ctx)
    assert decision.decision == GatewayDecisionEnum.ALLOW
    assert decision.requires_human_approval is False
    assert decision.policy_version.startswith("finance-v3")
    assert len(worker.sent_notifications) == 1
    
    wf = memory_bank.get_workflow(proposal.workflow_id)
    assert wf is not None
    assert wf.state == WorkflowState.COMPLETED

def test_gateway_require_human_approval_medium_risk(setup_gateway):
    gateway, id_provider, worker, memory_bank = setup_gateway
    token = id_provider.generate_agent_token("finance-agent", "1.2.0")
    
    # 20,000 INR -> Requires Human Approval in finance-v3 (5,000 to 25,000)
    proposal = AgentActionProposal(
        agent_id="finance-agent",
        agent_version="1.2.0",
        action_name="issue_refund",
        target_resource_id="REF-202",
        amount=Decimal("20000.00"),
        currency="INR",
        recipient="enterprise.client@company.com",
        justification="Commercial agreement refund settlement"
    )
    auth_ctx = AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0", token=token)
    
    decision = gateway.authorize_action(proposal, auth_ctx)
    assert decision.decision == GatewayDecisionEnum.REQUIRE_HUMAN_APPROVAL
    assert decision.requires_human_approval is True
    # Side effect must NOT be executed yet
    assert len(worker.sent_notifications) == 0
    
    # Workflow should be paused in Memory Bank
    wf = memory_bank.get_workflow(proposal.workflow_id)
    assert wf.state == WorkflowState.PAUSED_FOR_APPROVAL
    
    # Check pending action queue
    pending = gateway.list_pending_actions()
    assert len(pending) == 1
    assert pending[0]["action_id"] == decision.action_record_id
    
    # Human Operator signs off
    app_dec = gateway.approve_action(decision.action_record_id, operator="Sarah Chief Risk Officer", notes="Verified contract terms")
    assert app_dec.decision == GatewayDecisionEnum.ALLOW
    assert len(worker.sent_notifications) == 1
    
    # Workflow resumed and completed
    wf_updated = memory_bank.get_workflow(proposal.workflow_id)
    assert wf_updated.state == WorkflowState.COMPLETED
    assert wf_updated.approval_record.status == "approved"
    assert wf_updated.approval_record.decided_by == "Sarah Chief Risk Officer"

def test_gateway_deny_high_risk_ceiling(setup_gateway):
    gateway, id_provider, worker, memory_bank = setup_gateway
    token = id_provider.generate_agent_token("finance-agent", "1.2.0")
    
    # 100,000 INR -> Exceeds 25,000 ceiling -> DENIED
    proposal = AgentActionProposal(
        agent_id="finance-agent",
        agent_version="1.2.0",
        action_name="issue_refund",
        target_resource_id="REF-303",
        amount=Decimal("100000.00"),
        currency="INR",
        recipient="client@company.com",
        justification="Full contract termination refund"
    )
    auth_ctx = AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0", token=token)
    
    decision = gateway.authorize_action(proposal, auth_ctx)
    assert decision.decision == GatewayDecisionEnum.DENY
    assert decision.requires_human_approval is False
    assert len(worker.sent_notifications) == 0
    assert "exceeds corporate authorization ceiling" in decision.reason
    
    wf = memory_bank.get_workflow(proposal.workflow_id)
    assert wf.state == WorkflowState.FAILED

def test_gateway_human_rejection(setup_gateway):
    gateway, id_provider, worker, memory_bank = setup_gateway
    token = id_provider.generate_agent_token("finance-agent", "1.2.0")
    
    proposal = AgentActionProposal(
        agent_id="finance-agent",
        agent_version="1.2.0",
        action_name="issue_refund",
        target_resource_id="REF-404",
        amount=Decimal("12000.00"),
        currency="INR",
        recipient="suspicious.claimant@company.com",
        justification="Questionable dispute"
    )
    auth_ctx = AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0", token=token)
    
    decision = gateway.authorize_action(proposal, auth_ctx)
    assert decision.decision == GatewayDecisionEnum.REQUIRE_HUMAN_APPROVAL
    
    # Operator Rejects
    rej_dec = gateway.reject_action(decision.action_record_id, operator="Audit Officer Bob", notes="Fraud indicator triggered")
    assert rej_dec.decision == GatewayDecisionEnum.DENY
    assert len(worker.sent_notifications) == 0
    
    wf = memory_bank.get_workflow(proposal.workflow_id)
    assert wf.state == WorkflowState.REJECTED
    assert wf.approval_record.status == "rejected"
