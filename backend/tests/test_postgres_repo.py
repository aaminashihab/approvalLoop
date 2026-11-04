"""
PostgresRepository against a real PostgreSQL server.

Uses TEST_DATABASE_URL when set (CI runs a postgres service), otherwise starts an embedded server
via the `pgserver` package. Every test gets its own schema, dropped afterwards.
"""
import os
import threading
import uuid
from datetime import timedelta
from decimal import Decimal

import psycopg
import pytest

from approval_loop.agent.drafter import GeminiAgentDrafter
from approval_loop.config import AppEnvironment, Settings
from approval_loop.domain.agent_registry import AgentRegistryService, AgentStatus
from approval_loop.domain.gateway_models import AgentActionProposal, AgentAuthContext, GatewayDecisionEnum
from approval_loop.domain.models import ActionRecord, ActionStatus, ActionType, ExpenseReport, ReportStatus, utc_now
from approval_loop.domain.registry import ApproverRegistry
from approval_loop.engine import ApprovalEngine
from approval_loop.gateway.gateway import AgentGateway
from approval_loop.guardrails.safety_guardrail import ModelSafetyGuardrail
from approval_loop.identity.auth_provider import AgentIdentityProvider
from approval_loop.memory.memory_bank import MemoryBankService, WorkflowMemoryRecord, WorkflowState
from approval_loop.policy.policy_engine import PolicyEngine
from approval_loop.runtime.async_runtime import AsyncTaskRecord
from approval_loop.storage.postgres_repo import PostgresRepository
from approval_loop.validator.validator import DeterministicValidator
from approval_loop.worker.worker import MockNotificationProvider


@pytest.fixture(scope="session")
def pg_dsn(tmp_path_factory):
    dsn = os.getenv("TEST_DATABASE_URL")
    if dsn:
        yield dsn
        return
    pgserver = pytest.importorskip("pgserver", reason="set TEST_DATABASE_URL or install pgserver")
    server = pgserver.get_server(str(tmp_path_factory.mktemp("pgdata")), cleanup_mode="stop")
    yield server.get_uri()


@pytest.fixture
def schema(pg_dsn):
    name = f"t_{uuid.uuid4().hex[:12]}"
    yield name
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')


@pytest.fixture
def repo(pg_dsn, schema):
    r = PostgresRepository(pg_dsn, schema=schema, max_size=8)
    yield r
    r.close()


def _gateway(repo):
    registry = AgentRegistryService(repo=repo)
    ids = AgentIdentityProvider(registry_service=registry, secret_key="pg-secret")
    memory = MemoryBankService(repo=repo)
    worker = MockNotificationProvider()
    gw = AgentGateway(registry=registry, identity_provider=ids, policy_engine=PolicyEngine(),
                      memory_bank=memory, worker=worker, guardrail=ModelSafetyGuardrail())
    return gw, ids, registry, memory, worker


def _refund(gw, ids, amount="20000.00", target=None):
    p = AgentActionProposal(agent_id="finance-agent", agent_version="1.2.0", action_name="issue_refund",
                            target_resource_id=target or f"REF-{uuid.uuid4().hex[:6]}", amount=Decimal(amount),
                            currency="INR", recipient="c@client.com", justification="Subscription dispute.")
    ctx = AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0",
                           token=ids.generate_agent_token("finance-agent", "1.2.0"))
    return p, gw.authorize_action(p, ctx)


def _report(rid, status=ReportStatus.PENDING, age_s=0, **kw):
    return ExpenseReport(report_id=rid, status=status, submitter_name="Alice", submitter_email="alice@company.com",
                         approver_email="approver1@co.com", backup_approver_email="backup1@co.com",
                         amount=Decimal("150.00"), currency="USD", description="Lunch",
                         submitted_at=utc_now() - timedelta(seconds=age_s), **kw)


# ---------------------------------------------------------------- basic persistence
def test_reports_round_trip_and_resolve(repo):
    repo.save_report(_report("EXP-1"))
    repo.save_report(_report("EXP-2"))
    assert {r.report_id for r in repo.list_open_reports()} == {"EXP-1", "EXP-2"}
    resolved = repo.resolve_report("EXP-1")
    assert resolved.status == ReportStatus.RESOLVED and resolved.resolved_at is not None
    assert [r.report_id for r in repo.list_open_reports()] == ["EXP-2"]
    assert repo.get_report("EXP-1").amount == Decimal("150.00")
    assert repo.resolve_report("missing") is None


def test_data_survives_a_new_connection_pool(pg_dsn, schema, repo):
    gw, ids, *_ = _gateway(repo)
    p, _ = _refund(gw, ids)
    second = PostgresRepository(pg_dsn, schema=schema)  # e.g. after a restart, or another instance
    try:
        assert second.get_workflow_memory(p.workflow_id).state == WorkflowState.PAUSED_FOR_APPROVAL
        assert {a.agent_id for a in second.list_agent_registrations()} >= {"finance-agent", "sales-agent", "support-agent"}
    finally:
        second.close()


# ---------------------------------------------------------------- gateway and human approval
def test_held_proposal_is_listed_and_approvable(repo):
    gw, ids, _, memory, worker = _gateway(repo)
    p, d = _refund(gw, ids)
    assert d.decision == GatewayDecisionEnum.REQUIRE_HUMAN_APPROVAL
    pending = gw.list_pending_actions()
    assert [x["proposal"]["target_resource_id"] for x in pending] == [p.target_resource_id]
    result = gw.approve_action(pending[0]["action_id"], operator="op", notes="ok")
    assert result.details["execution_ok"] is True
    assert gw.list_pending_actions() == []
    wf = memory.get_workflow(p.workflow_id)
    assert wf.state == WorkflowState.COMPLETED and wf.approval_record.decided_by == "op"
    assert len(worker.sent_notifications) == 1


def test_denied_and_inactive_agent_paths(repo):
    gw, ids, registry, memory, _ = _gateway(repo)
    p_deny, d = _refund(gw, ids, amount="100000.00")
    assert d.decision == GatewayDecisionEnum.DENY
    assert memory.get_workflow(p_deny.workflow_id).state == WorkflowState.DENIED
    _refund(gw, ids)
    action_id = gw.list_pending_actions()[0]["action_id"]
    registry.update_agent_status("finance-agent", AgentStatus.DISABLED)
    with pytest.raises(ValueError, match="no longer ACTIVE"):
        gw.approve_action(action_id, operator="op")
    assert [x["action_id"] for x in gw.list_pending_actions()] == [action_id]


def test_approval_race_across_instances_has_one_winner(pg_dsn, schema, repo):
    """Two API instances = two connection pools and two Memory Banks with separate locks."""
    gw, ids, *_ = _gateway(repo)
    _refund(gw, ids)
    action_id = gw.list_pending_actions()[0]["action_id"]
    other = PostgresRepository(pg_dsn, schema=schema, max_size=8)
    banks = [MemoryBankService(repo=repo), MemoryBankService(repo=other)]
    barrier = threading.Barrier(16)
    winners = []

    def go(i):
        barrier.wait()
        ok, _, _ = banks[i % 2].claim_and_transition_approval(action_id, approve=True, operator=f"op-{i}")
        if ok:
            winners.append(f"op-{i}")
    try:
        threads = [threading.Thread(target=go, args=(i,)) for i in range(16)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert len(winners) == 1
        stored = repo.find_workflow_memory_by_action_id(action_id)
        assert stored.state == WorkflowState.APPROVED and stored.approval_record.decided_by == winners[0]
    finally:
        other.close()


def test_stale_compare_and_set_is_refused(repo):
    rec = WorkflowMemoryRecord(workflow_id="wf-1", agent_id="finance-agent", state=WorkflowState.PAUSED_FOR_APPROVAL)
    rec.approval_record.action_id = "act-1"
    repo.save_workflow_memory(rec)
    stale = repo.find_workflow_memory_by_action_id("act-1")
    winner = stale.model_copy(deep=True)
    winner.state = WorkflowState.APPROVED
    assert repo.compare_and_set_workflow_memory(winner, "paused_for_approval") is True
    stale.state = WorkflowState.REJECTED
    assert repo.compare_and_set_workflow_memory(stale, "paused_for_approval") is False
    assert repo.get_workflow_memory("wf-1").state == WorkflowState.APPROVED
    assert repo.find_workflow_memory_by_action_id("missing") is None


def test_list_workflows_filters(repo):
    for wid, agent, state in [("a", "finance-agent", WorkflowState.PAUSED_FOR_APPROVAL),
                              ("b", "finance-agent", WorkflowState.COMPLETED),
                              ("c", "sales-agent", WorkflowState.PAUSED_FOR_APPROVAL)]:
        repo.save_workflow_memory(WorkflowMemoryRecord(workflow_id=wid, agent_id=agent, state=state))
    assert {r.workflow_id for r in repo.list_workflow_memories()} == {"a", "b", "c"}
    assert {r.workflow_id for r in repo.list_workflow_memories(agent_id="finance-agent")} == {"a", "b"}
    assert {r.workflow_id for r in repo.list_workflow_memories(state="paused_for_approval")} == {"a", "c"}
    assert [r.workflow_id for r in repo.list_workflow_memories(agent_id="sales-agent", state="completed")] == []


def test_daily_cap_counts_persisted_decisions(repo):
    gw, ids, *_ = _gateway(repo)
    outcomes = [_refund(gw, ids, amount="4999.00")[1].decision for _ in range(11)]
    assert outcomes[:10] == [GatewayDecisionEnum.ALLOW] * 10
    assert outcomes[10] == GatewayDecisionEnum.REQUIRE_HUMAN_APPROVAL


# ---------------------------------------------------------------- expense reminder loop
def _engine(repo, worker=None):
    settings = Settings(app_env=AppEnvironment.TEST)
    registry = ApproverRegistry(admin_fallback_email="admin@company.internal")
    registry.register_approver("approver1@co.com", "backup1@co.com")
    return ApprovalEngine(repo, settings, registry, GeminiAgentDrafter(api_key=None),
                          DeterministicValidator(registry=registry), worker or MockNotificationProvider())


def test_tick_persists_completed_actions_and_never_duplicates(repo):
    engine = _engine(repo)
    nudge_after = engine.settings.thresholds.nudge_threshold_seconds
    repo.save_report(_report("EXP-OLD", age_s=nudge_after + 5))
    repo.save_report(_report("EXP-NEW", age_s=0))
    first = engine.run_tick(tick_id="t1")
    assert [a.report_id for a in first] == ["EXP-OLD"]
    stored = repo.list_all_actions()
    assert len(stored) == 1
    a = stored[0]
    # Fields set in memory after the claim must have been persisted (draft, envelope, validator, transition).
    assert a.status == ActionStatus.COMPLETED and a.message and a.envelope is not None
    assert a.validator_result is not None and a.sent_at is not None and a.state_transition.value == "applied"
    assert repo.get_report("EXP-OLD").status == ReportStatus.NUDGED
    assert engine.run_tick(tick_id="t2") == []
    assert len(repo.list_all_actions()) == 1


def test_failed_delivery_keeps_the_draft_and_counts_the_attempt(repo):
    worker = MockNotificationProvider()
    worker.simulate_failure = True
    engine = _engine(repo, worker)
    repo.save_report(_report("EXP-F", age_s=engine.settings.thresholds.nudge_threshold_seconds + 5))
    engine.run_tick(tick_id="t1")
    (a,) = repo.list_all_actions()
    assert a.status == ActionStatus.FAILED and a.attempt_count == 1 and a.last_error
    assert a.message, "drafted wording was lost when recording the failure"


def test_concurrent_claims_for_one_action_have_one_winner(repo):
    repo.save_report(_report("EXP-C"))
    barrier = threading.Barrier(8)
    results = []

    def go():
        candidate = ActionRecord(report_id="EXP-C", action_type=ActionType.NUDGE, source_state=ReportStatus.PENDING,
                                 target_state=ReportStatus.NUDGED, tick_id="t", idempotency_key="EXP-C:nudge",
                                 recipient="approver1@co.com", amount=Decimal("150.00"))
        barrier.wait()
        results.append(repo.claim_action_transaction(candidate)[0])
    threads = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(True) == 1
    assert len(repo.list_all_actions()) == 1


# ---------------------------------------------------------------- async tasks
def test_async_task_lookup_by_idempotency_key(repo):
    task = AsyncTaskRecord(workflow_id="wf-9", proposal_id="p-9", idempotency_key="async:finance-agent:issue_refund:REF-9",
                           agent_id="finance-agent", action_name="issue_refund")
    repo.save_async_task(task)
    found = repo.get_async_task_by_idempotency_key(task.idempotency_key)
    assert found.task_id == task.task_id
    task.status = "completed"
    repo.save_async_task(task)
    assert [t.task_id for t in repo.list_async_tasks(status="completed")] == [task.task_id]
    assert repo.get_async_task("missing") is None
