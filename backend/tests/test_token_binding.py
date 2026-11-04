"""
Agent tokens bound to one request and one proposal (defect D7).

Before: the HMAC token covered only agent, version and expiry, so a captured token could be
replayed with fresh request_ids and arbitrary proposals until it expired (paper, experiment E4).
"""
import json
from decimal import Decimal

import pytest

from approval_loop.agent.fleet import FinanceAgent, SalesAgent
from approval_loop.domain.agent_registry import AgentRegistryService
from approval_loop.domain.gateway_models import AgentActionProposal, AgentAuthContext, GatewayDecisionEnum
from approval_loop.gateway.gateway import AgentGateway
from approval_loop.guardrails.safety_guardrail import ModelSafetyGuardrail
from approval_loop.identity.auth_provider import AgentIdentityProvider, proposal_digest
from approval_loop.memory.memory_bank import MemoryBankService
from approval_loop.policy.policy_engine import PolicyEngine
from approval_loop.worker.worker import MockNotificationProvider


@pytest.fixture
def strict():
    registry = AgentRegistryService()
    ids = AgentIdentityProvider(registry_service=registry, secret_key="bind-secret", require_request_binding=True)
    gw = AgentGateway(registry=registry, identity_provider=ids, policy_engine=PolicyEngine(),
                      memory_bank=MemoryBankService(), worker=MockNotificationProvider(), guardrail=ModelSafetyGuardrail())
    return gw, ids


def _proposal(amount="100.00", **kw):
    return AgentActionProposal(agent_id="finance-agent", agent_version="1.2.0", action_name="issue_refund",
                               target_resource_id=kw.pop("target", "REF-1"), amount=Decimal(amount), currency="INR",
                               recipient="customer@client.com", justification="Damaged item.", **kw)


def _bound(ids, proposal, request_id="req-1"):
    token = ids.generate_agent_token("finance-agent", "1.2.0", request_id=request_id, proposal=proposal)
    return AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0", token=token, request_id=request_id)


def test_bound_token_is_accepted(strict):
    gw, ids = strict
    p = _proposal()
    assert gw.authorize_action(p, _bound(ids, p)).identity_verified


def test_unbound_token_is_rejected_when_binding_is_required(strict):
    gw, ids = strict
    p = _proposal()
    ctx = AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0",
                           token=ids.generate_agent_token("finance-agent", "1.2.0"))
    d = gw.authorize_action(p, ctx)
    assert d.decision == GatewayDecisionEnum.DENY and "Unbound Agent Token" in d.reason


def test_captured_token_cannot_be_reused_with_fresh_request_ids(strict):
    gw, ids = strict
    p = _proposal()
    ctx = _bound(ids, p, request_id="req-original")
    assert gw.authorize_action(p, ctx).identity_verified
    for i in range(5):
        replay = AgentAuthContext(**{**ctx.model_dump(), "request_id": f"fresh-{i}"})
        d = gw.authorize_action(_proposal(target=f"REF-NEW-{i}"), replay)
        assert not d.identity_verified, d.reason


def test_token_cannot_authorise_a_different_amount(strict):
    gw, ids = strict
    p = _proposal(amount="100.00")
    ctx = _bound(ids, p)
    tampered = p.model_copy(update={"amount": Decimal("4999.00")})
    d = gw.authorize_action(tampered, ctx)
    assert d.decision == GatewayDecisionEnum.DENY and "proposal content differs" in d.reason


def test_digest_survives_a_json_round_trip():
    """The gateway re-parses proposals from HTTP JSON; the digest must not depend on representation."""
    for agent_proposal in [
        _proposal(amount="20000.00", parameters={"refund_id": "REF-1", "amount": "20000.00"}),
        AgentActionProposal(agent_id="sales-agent", agent_version="1.0.0", action_name="grant_discount",
                            target_resource_id="DEAL-1", amount=Decimal("120000"), currency="USD",
                            recipient="cfo@client.com", parameters={"discount_percent": 18.5}),
    ]:
        wire = json.loads(json.dumps(agent_proposal.to_dict()))
        assert proposal_digest(AgentActionProposal(**wire)) == proposal_digest(agent_proposal)
    base = _proposal(amount="20000.00")
    same_amount_other_format = base.model_copy(update={"amount": Decimal("20000")})
    assert proposal_digest(same_amount_other_format) == proposal_digest(base)
    assert proposal_digest(base.model_copy(update={"amount": Decimal("20000.01")})) != proposal_digest(base)


def test_fleet_agents_issue_bound_tokens_that_pass_a_strict_gateway(strict):
    gw, ids = strict
    proposal, ctx = FinanceAgent(identity_provider=ids).propose_refund("REF-F1", "c@client.com", Decimal("1000.00"))
    assert gw.authorize_action(proposal, ctx).identity_verified
    proposal, ctx = SalesAgent(identity_provider=ids).propose_discount("DEAL-9", "cfo@client.com", 5.0, Decimal("50000"))
    assert gw.authorize_action(proposal, ctx).identity_verified
