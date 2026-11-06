"""
Daily autonomous-value cap per agent and currency.

Per-action limits alone let an agent (or a stolen credential) issue many proposals just under the
auto-approve limit; each one executes. The cap holds further proposals for a person once the day's
autonomously executed total would exceed the policy's daily_auto_cap.
"""
import threading
from datetime import timedelta
from decimal import Decimal

from approval_loop.domain.agent_registry import AgentRegistryService
from approval_loop.domain.gateway_models import AgentActionProposal, AgentAuthContext, GatewayDecisionEnum, utc_now
from approval_loop.gateway.gateway import AgentGateway
from approval_loop.guardrails.safety_guardrail import ModelSafetyGuardrail
from approval_loop.identity.auth_provider import AgentIdentityProvider
from approval_loop.memory.memory_bank import MemoryBankService
from approval_loop.policy.policy_engine import PolicyEngine
from approval_loop.storage.memory_repo import InMemoryRepository
from approval_loop.worker.worker import MockNotificationProvider


def _gateway(enforce=True):
    repo = InMemoryRepository()
    registry = AgentRegistryService(repo=repo)
    ids = AgentIdentityProvider(registry_service=registry, secret_key="cap-secret")
    worker = MockNotificationProvider()
    gw = AgentGateway(registry=registry, identity_provider=ids, policy_engine=PolicyEngine(enforce_daily_caps=enforce),
                      memory_bank=MemoryBankService(repo=repo), worker=worker, guardrail=ModelSafetyGuardrail())
    return gw, ids, worker


def _send(gw, ids, amount, currency="INR"):
    p = AgentActionProposal(agent_id="finance-agent", agent_version="1.2.0", action_name="issue_refund",
                            target_resource_id="REF-CAP", amount=Decimal(amount), currency=currency,
                            recipient="c@client.com", justification="Refund.")
    ctx = AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0",
                           token=ids.generate_agent_token("finance-agent", "1.2.0"))
    return gw.authorize_action(p, ctx)


def test_many_small_refunds_stop_auto_executing_at_the_cap():
    gw, ids, worker = _gateway()
    outcomes = [_send(gw, ids, "4999.00").decision for _ in range(12)]
    # 10 x 4,999 = 49,990 fits under 50,000; the 11th would reach 54,989.
    assert outcomes[:10] == [GatewayDecisionEnum.ALLOW] * 10
    assert outcomes[10:] == [GatewayDecisionEnum.REQUIRE_HUMAN_APPROVAL] * 2
    assert len(worker.sent_notifications) == 10
    held = gw.list_pending_actions()
    assert len(held) == 2 and "DAILY_AUTO_CAP" in held[0]["decision"]["reason"]


def test_cap_is_per_currency_and_ignores_previous_days():
    gw, ids, _ = _gateway()
    for _ in range(10):
        _send(gw, ids, "4999.00")
    assert _send(gw, ids, "40.00", currency="USD").decision == GatewayDecisionEnum.ALLOW
    # Age every recorded decision by one day: yesterday's spending no longer counts.
    for wf in gw.memory_bank.list_workflows():
        for d in wf.previous_decisions:
            d["timestamp"] = (utc_now() - timedelta(days=1)).isoformat()
        gw.memory_bank.save_workflow(wf)
    assert _send(gw, ids, "4999.00").decision == GatewayDecisionEnum.ALLOW


def test_concurrent_proposals_cannot_overshoot_the_cap():
    gw, ids, worker = _gateway()
    barrier = threading.Barrier(20)
    results = []

    def go():
        barrier.wait()
        results.append(_send(gw, ids, "4000.00").decision)
    threads = [threading.Thread(target=go) for _ in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(GatewayDecisionEnum.ALLOW) == 12  # 12 x 4,000 = 48,000 <= 50,000 < 13 x 4,000
    assert len(worker.sent_notifications) == 12


def test_cap_can_be_disabled_for_benchmarks():
    gw, ids, _ = _gateway(enforce=False)
    assert all(_send(gw, ids, "4999.00").decision == GatewayDecisionEnum.ALLOW for _ in range(15))


def test_cap_lock_is_released_when_the_cap_check_fails():
    """A storage error during the cap check must not leave the lock held (it used to stall every later ALLOW)."""
    gw, ids, _ = _gateway()
    real_list = gw.memory_bank.list_workflows
    calls = {"n": 0}

    def flaky_list(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated storage error")
        return real_list(*args, **kwargs)

    gw.memory_bank.list_workflows = flaky_list
    try:
        _send(gw, ids, "100.00")
        raise AssertionError("the simulated storage error should propagate")
    except RuntimeError:
        pass

    result = {}
    t = threading.Thread(target=lambda: result.setdefault("d", _send(gw, ids, "100.00")), daemon=True)
    t.start()
    t.join(timeout=5)
    assert not t.is_alive(), "second proposal hung: the daily-cap lock was never released"
    assert result["d"].decision == GatewayDecisionEnum.ALLOW
