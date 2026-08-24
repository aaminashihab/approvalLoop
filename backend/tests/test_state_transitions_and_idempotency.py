import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from approval_loop.config import Settings, AppEnvironment
from approval_loop.domain.models import ExpenseReport, ReportStatus, ActionStatus, StateTransitionResult, NotificationEnvelope, utc_now
from approval_loop.domain.registry import ApproverRegistry
from approval_loop.storage.memory_repo import InMemoryRepository
from approval_loop.engine import ApprovalEngine
from approval_loop.agent.drafter import GeminiAgentDrafter
from approval_loop.validator.validator import DeterministicValidator
from approval_loop.policy.policy_engine import PolicyEngine
from approval_loop.guardrails.safety_guardrail import ModelSafetyGuardrail
from approval_loop.worker.worker import MockNotificationWorker, SlackNotificationProvider, EmailNotificationProvider
from approval_loop.domain.agent_registry import AgentRegistryService, AgentRegistration, AgentStatus, RiskLevel
from approval_loop.identity.auth_provider import AgentIdentityProvider
from approval_loop.domain.gateway_models import AgentActionProposal, AgentAuthContext


def _make_engine(repo, worker):
    settings = Settings(app_env=AppEnvironment.TEST)
    registry = ApproverRegistry(admin_fallback_email="admin@company.com")
    registry.register_approver("bob@company.com", "marcus.director@company.com")
    registry.register_approver("dan@company.com", "marcus.director@company.com")
    registry.register_approver("frank@company.com", "marcus.director@company.com")
    validator = DeterministicValidator(registry=registry)
    drafter = GeminiAgentDrafter()
    return ApprovalEngine(repo, settings, registry, drafter, validator, worker)


def test_human_state_wins_on_pending_to_approved_during_agent_nudge():
    """
    Phase 7 Invariant: Human action wins over in-flight agent action.
    Report: PENDING. Human resolves report to APPROVED while agent nudge is processing.
    Asserts: Agent transition is SKIPPED, report remains RESOLVED/APPROVED, 0 stale sends.
    """
    repo = InMemoryRepository()
    now = utc_now()
    report = ExpenseReport(
        report_id="EXP-HUMAN-WIN-01",
        submitter_name="Alice",
        submitter_email="alice@company.com",
        approver_email="bob@company.com",
        amount=Decimal("150.00"),
        currency="USD",
        description="Office Supplies",
        status=ReportStatus.PENDING,
        submitted_at=now - timedelta(seconds=10)
    )
    repo.save_report(report)

    worker = MockNotificationWorker()
    sent_envelopes = []
    def _intercept_send(envelope, idempotency_key):
        sent_envelopes.append(envelope)
        return True, "notif-intercepted", None
    worker.send = _intercept_send

    engine = _make_engine(repo, worker)

    # Intercept mid-flight: Simulate human resolving report right after policy check
    orig_policy = engine.policy_engine.evaluate
    def _mid_flight_human_resolve(action, report_obj, envelope):
        res = orig_policy(action, report_obj, envelope)
        repo.resolve_report("EXP-HUMAN-WIN-01")  # Human resolves report to APPROVED/RESOLVED
        return res
    engine.policy_engine.evaluate = _mid_flight_human_resolve

    actions = engine.run_tick("tick_human_win_test_1")

    assert len(actions) == 1
    action = actions[0]
    assert action.state_transition == StateTransitionResult.SKIPPED
    assert "report state changed" in action.skip_reason.lower() or "resolved" in action.skip_reason.lower()
    assert len(sent_envelopes) == 0  # Stale notification was NOT sent!
    assert repo.get_report("EXP-HUMAN-WIN-01").status == ReportStatus.RESOLVED


def test_human_state_wins_on_nudged_to_approved_during_agent_escalate():
    """
    Phase 7 Invariant: Human action wins on NUDGED -> APPROVED while agent attempts NUDGED -> ESCALATED.
    Asserts: Agent escalation is SKIPPED, report remains RESOLVED.
    """
    repo = InMemoryRepository()
    now = utc_now()
    report = ExpenseReport(
        report_id="EXP-HUMAN-WIN-02",
        submitter_name="Charlie",
        submitter_email="charlie@company.com",
        approver_email="dan@company.com",
        amount=Decimal("450.00"),
        currency="USD",
        description="Conference Pass",
        status=ReportStatus.NUDGED,
        nudge_count=1,
        last_nudged_at=now - timedelta(seconds=35),
        submitted_at=now - timedelta(seconds=50)
    )
    repo.save_report(report)

    worker = MockNotificationWorker()
    engine = _make_engine(repo, worker)

    # Human resolves report right before pre-dispatch check during policy evaluation
    orig_policy = engine.policy_engine.evaluate
    def _mid_flight_human_resolve(action, report_obj, envelope):
        res = orig_policy(action, report_obj, envelope)
        repo.resolve_report("EXP-HUMAN-WIN-02")
        return res
    engine.policy_engine.evaluate = _mid_flight_human_resolve

    actions = engine.run_tick("tick_human_win_test_2")

    assert len(actions) == 1
    assert actions[0].state_transition == StateTransitionResult.SKIPPED
    assert repo.get_report("EXP-HUMAN-WIN-02").status == ReportStatus.RESOLVED


def test_action_key_idempotency_prevents_duplicates_on_repeated_ticks():
    """
    Phase 6 Invariant: Action key idempotency prevents duplicate actions across repeated scheduler ticks.
    Asserts: Tick 1 executes nudge. Tick 2 produces 0 duplicate actions.
    """
    repo = InMemoryRepository()
    now = utc_now()
    report = ExpenseReport(
        report_id="EXP-IDEMPOTENCY-01",
        submitter_name="Eve",
        submitter_email="eve@company.com",
        approver_email="frank@company.com",
        amount=Decimal("200.00"),
        currency="USD",
        description="Team Lunch",
        status=ReportStatus.PENDING,
        submitted_at=now - timedelta(seconds=10)
    )
    repo.save_report(report)

    worker = MockNotificationWorker()
    engine = _make_engine(repo, worker)

    # Tick 1: Autonomous Nudge Executed
    actions_tick_1 = engine.run_tick("tick_1")
    assert len(actions_tick_1) == 1
    assert actions_tick_1[0].status == ActionStatus.COMPLETED
    assert repo.get_report("EXP-IDEMPOTENCY-01").status == ReportStatus.NUDGED

    # Tick 2: Repeated Scheduler Tick immediately afterwards
    actions_tick_2 = engine.run_tick("tick_2")
    assert len(actions_tick_2) == 0  # Zero duplicate actions!


def test_distributed_replay_protection_blocks_replayed_request_id():
    """
    Phase 4 Invariant: Distributed Replay Protection detects and blocks duplicate request_ids
    across multiple isolated AgentIdentityProvider instances using shared repository.
    """
    repo = InMemoryRepository()
    registry = AgentRegistryService(repo=repo)
    registry.register_agent(AgentRegistration(
        agent_id="test-agent",
        name="Test Agent",
        description="Test agent instance",
        owner="SecOps",
        version="1.0.0",
        status=AgentStatus.ACTIVE,
        risk_level=RiskLevel.LOW,
        allowed_actions=["test_action"]
    ))

    # Cloud Run Node 1 Identity Provider
    provider_node_1 = AgentIdentityProvider(registry_service=registry, secret_key="shared-secret-key")
    # Cloud Run Node 2 Identity Provider (separate instance, same repo)
    provider_node_2 = AgentIdentityProvider(registry_service=registry, secret_key="shared-secret-key")

    token = provider_node_1.generate_agent_token("test-agent", "1.0.0")
    proposal = AgentActionProposal(
        agent_id="test-agent",
        agent_version="1.0.0",
        action_name="test_action",
        target_resource_id="RES-01",
        recipient="target@company.com",
        amount=Decimal("10.00")
    )
    auth_ctx = AgentAuthContext(
        agent_id="test-agent",
        agent_version="1.0.0",
        token=token,
        request_id="req-unique-uuid-999"
    )

    # 1. Request on Cloud Run Node 1 -> Passes
    ok1, reason1, _ = provider_node_1.verify_agent_request(proposal, auth_ctx)
    assert ok1 is True
    assert "authenticated successfully" in reason1

    # 2. Replayed Request on Cloud Run Node 2 -> Blocked!
    ok2, reason2, _ = provider_node_2.verify_agent_request(proposal, auth_ctx)
    assert ok2 is False
    assert "Replay Attack Prevented" in reason2


def test_slack_and_email_notification_provider_dry_runs():
    """
    Phase 12 Invariant: Slack and Email notification adapters run safely in dry-run mode.
    """
    slack_provider = SlackNotificationProvider()
    email_provider = EmailNotificationProvider()

    envelope = NotificationEnvelope(
        recipient="test@company.com",
        subject="Test Approval Request",
        body_text="Please approve expense EXP-100",
        amount=Decimal("100.00"),
        currency="USD",
        submitter_name="Test Submitter",
        report_id="EXP-100"
    )

    ok_slack, receipt_slack, err_slack = slack_provider.send(envelope, "key_slack_1")
    assert ok_slack is True
    assert "slack_dry_run" in receipt_slack
    assert err_slack is None

    ok_email, receipt_email, err_email = email_provider.send(envelope, "key_email_1")
    assert ok_email is True
    assert "email_dry_run" in receipt_email
    assert err_email is None
