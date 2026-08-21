import os
import sys
from decimal import Decimal

# Ensure backend package is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from approval_loop.domain.agent_registry import AgentRegistryService
from approval_loop.identity.auth_provider import AgentIdentityProvider
from approval_loop.guardrails.safety_guardrail import ModelSafetyGuardrail
from approval_loop.policy.policy_engine import PolicyEngine
from approval_loop.memory.memory_bank import MemoryBankService, WorkflowState
from approval_loop.worker.worker import MockNotificationProvider
from approval_loop.gateway.gateway import AgentGateway
from approval_loop.agent.fleet import FinanceAgent, SupportAgent, SalesAgent
from approval_loop.domain.gateway_models import GatewayDecisionEnum

def run_fleet_demo():
    print("=" * 85)
    print("APPROVALLOOP -- FORTIFIED ENTERPRISE FLEET GOVERNANCE DEMONSTRATION")
    print("Core Invariant: 'AI proposes. Deterministic policy decides. Infrastructure executes.'")
    print("=" * 85)

    registry = AgentRegistryService()
    id_provider = AgentIdentityProvider(registry_service=registry, secret_key="demo-master-key")
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

    finance_agent = FinanceAgent(identity_provider=id_provider)
    support_agent = SupportAgent(identity_provider=id_provider)
    sales_agent = SalesAgent(identity_provider=id_provider)

    # -------------------------------------------------------------------------
    # CASE A: Low-Risk Action (< INR 5,000 / $50) -> Auto-ALLOW
    # -------------------------------------------------------------------------
    print("\n[CASE A] Finance Agent requests Refund of INR 2,000 ($20) -> Automatic ALLOW")
    prop_a, auth_a = finance_agent.propose_refund(
        refund_id="REF-101",
        customer_email="alice.client@customer.com",
        amount=Decimal("2000.00"),
        currency="INR",
        reason="Returned unopened accessory item within 7-day window"
    )
    dec_a = gateway.authorize_action(prop_a, auth_a)
    print(f"  -> Agent Identity:      VERIFIED ({auth_a.verification_method})")
    print(f"  -> Policy Profile:     {dec_a.policy_version}")
    print(f"  -> Gateway Decision:   {dec_a.decision.value.upper()}")
    print(f"  -> Reason:             {dec_a.reason}")
    print(f"  -> Side Effect Sent:   {'YES' if len(worker.sent_notifications) == 1 else 'NO'}")
    assert dec_a.decision == GatewayDecisionEnum.ALLOW
    assert len(worker.sent_notifications) == 1
    print("  [PASS] Case A executed automatically without human intervention.")

    # -------------------------------------------------------------------------
    # CASE B: Medium-Risk Action (INR 5,000 - INR 25,000 / $50 - $250) -> REQUIRE_HUMAN_APPROVAL
    # -------------------------------------------------------------------------
    print("\n[CASE B] Finance Agent requests Refund of INR 20,000 ($200) -> REQUIRE_HUMAN_APPROVAL")
    prop_b, auth_b = finance_agent.propose_refund(
        refund_id="REF-202",
        customer_email="bob.enterprise@customer.com",
        amount=Decimal("20000.00"),
        currency="INR",
        reason="Commercial enterprise refund request for delayed delivery"
    )
    dec_b = gateway.authorize_action(prop_b, auth_b)
    print(f"  -> Agent Identity:      VERIFIED ({auth_b.verification_method})")
    print(f"  -> Policy Profile:     {dec_b.policy_version}")
    print(f"  -> Gateway Decision:   {dec_b.decision.value.upper()} (Workflow Paused in Memory Bank)")
    print(f"  -> Reason:             {dec_b.reason}")
    print(f"  -> Action Record ID:   {dec_b.action_record_id}")
    
    # Verify side effect paused
    assert dec_b.decision == GatewayDecisionEnum.REQUIRE_HUMAN_APPROVAL
    assert len(worker.sent_notifications) == 1  # unchanged from case A
    
    wf_b = memory_bank.get_workflow(prop_b.workflow_id)
    assert wf_b.state == WorkflowState.PAUSED_FOR_APPROVAL
    print(f"  -> Memory Bank State:  {wf_b.state.value.upper()}")

    # Human sign-off in dashboard/API
    print("  -> Human Operator Signs Off in Dashboard...")
    app_dec = gateway.approve_action(dec_b.action_record_id, operator="Sarah Chief Risk Officer", notes="Verified SLA terms")
    print(f"  -> Resumed Decision:   {app_dec.decision.value.upper()}")
    print(f"  -> Execution Receipt:  {worker.sent_notifications[-1]['notification_id']}")
    assert len(worker.sent_notifications) == 2
    print("  [PASS] Case B workflow paused, awaited human sign-off, and resumed successfully.")

    # -------------------------------------------------------------------------
    # CASE C: High-Risk Action (> INR 25,000 / $250) -> DENY
    # -------------------------------------------------------------------------
    print("\n[CASE C] Finance Agent requests Refund of INR 100,000 ($1,000) -> Policy DENY")
    prop_c, auth_c = finance_agent.propose_refund(
        refund_id="REF-303",
        customer_email="carlos.contract@customer.com",
        amount=Decimal("100000.00"),
        currency="INR",
        reason="Settlement claim for full contract cancellation"
    )
    dec_c = gateway.authorize_action(prop_c, auth_c)
    print(f"  -> Agent Identity:      VERIFIED ({auth_c.verification_method})")
    print(f"  -> Policy Profile:     {dec_c.policy_version}")
    print(f"  -> Gateway Decision:   {dec_c.decision.value.upper()}")
    print(f"  -> Rejection Reason:   {dec_c.reason}")
    assert dec_c.decision == GatewayDecisionEnum.DENY
    assert len(worker.sent_notifications) == 2  # blocked, no new notification
    print("  [PASS] Case C denied deterministically. The LLM cannot bypass policy.")

    # -------------------------------------------------------------------------
    # SUPPORT & SALES FLEET AGENT VERIFICATION
    # -------------------------------------------------------------------------
    print("\n[FLEET EXPANSION] Testing Support Agent & Sales Agent Policies")
    # Support Agent Credit
    prop_sup, auth_sup = support_agent.propose_credit("TICK-808", "vip@client.com", Decimal("1500.00"), "INR", "SLA outage credit")
    dec_sup = gateway.authorize_action(prop_sup, auth_sup)
    print(f"  -> Support Agent (support-v1): Credit INR 1,500 -> {dec_sup.decision.value.upper()} (ALLOW)")
    assert dec_sup.decision == GatewayDecisionEnum.ALLOW

    # Sales Agent 25% Discount (requires VP Sales sign-off)
    prop_sales, auth_sales = sales_agent.propose_discount("DEAL-909", "cfo@target.com", 25.0, Decimal("150000.00"), "USD", "Multi-year deal")
    dec_sales = gateway.authorize_action(prop_sales, auth_sales)
    print(f"  -> Sales Agent (sales-v1): 25% Discount -> {dec_sales.decision.value.upper()} (REQUIRE_HUMAN_APPROVAL)")
    assert dec_sales.decision == GatewayDecisionEnum.REQUIRE_HUMAN_APPROVAL

    print("\n" + "=" * 85)
    print("FORTIFIED ENTERPRISE FLEET VERIFICATION COMPLETE: 100% SUCCESS")
    print("=" * 85)

if __name__ == "__main__":
    run_fleet_demo()
