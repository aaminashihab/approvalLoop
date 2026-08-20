import pytest
from datetime import timedelta
from decimal import Decimal
from approval_loop.domain.models import (
    ExpenseReport, ReportStatus, ActionStatus, StateTransitionResult,
    ValidatorResultEnum, ActionType, utc_now
)
from approval_loop.storage.memory_repo import InMemoryRepository
from approval_loop.config import Settings, AppEnvironment
from approval_loop.domain.registry import ApproverRegistry
from approval_loop.validator.validator import DeterministicValidator
from approval_loop.agent.drafter import GeminiAgentDrafter
from approval_loop.worker.worker import MockNotificationWorker
from approval_loop.engine import ApprovalEngine

@pytest.fixture
def setup_engine():
    repo = InMemoryRepository()
    settings = Settings(app_env=AppEnvironment.TEST)
    registry = ApproverRegistry(admin_fallback_email="admin-escalations@company.com")
    registry.register_approver("sarah.finance@company.com", "marcus.director@company.com")
    registry.register_approver("approver1@co.com", "backup1@co.com")
    validator = DeterministicValidator(registry=registry)
    drafter = GeminiAgentDrafter()
    worker = MockNotificationWorker()
    engine = ApprovalEngine(repo, settings, registry, drafter, validator, worker)
    return engine, repo, worker, registry

def test_scenario_1_fresh_pending_report(setup_engine):
    engine, repo, worker, _ = setup_engine
    report = ExpenseReport(
        report_id="EXP-101",
        submitter_name="Alice",
        submitter_email="alice@co.com",
        approver_email="sarah.finance@company.com",
        amount=Decimal("150.00"),
        description="Lunch catering",
        submitted_at=utc_now()
    )
    repo.save_report(report)
    actions = engine.run_tick("tick_1")
    assert len(actions) == 0
    assert repo.get_report("EXP-101").status == ReportStatus.PENDING

def test_scenario_2_pending_past_nudge_threshold(setup_engine):
    engine, repo, worker, _ = setup_engine
    report = ExpenseReport(
        report_id="EXP-102",
        submitter_name="Bob",
        submitter_email="bob@co.com",
        approver_email="sarah.finance@company.com",
        amount=Decimal("1250.00"),
        description="Software subscription",
        submitted_at=utc_now() - timedelta(seconds=10)
    )
    repo.save_report(report)
    actions = engine.run_tick("tick_2")
    assert len(actions) == 1
    action = actions[0]
    assert action.status == ActionStatus.COMPLETED
    assert action.state_transition == StateTransitionResult.APPLIED
    assert action.recipient == "sarah.finance@company.com"
    assert action.amount == Decimal("1250.00")
    assert repo.get_report("EXP-102").status == ReportStatus.NUDGED

def test_scenario_3_same_report_next_tick_before_escalation(setup_engine):
    engine, repo, worker, _ = setup_engine
    report = ExpenseReport(
        report_id="EXP-102",
        status=ReportStatus.NUDGED,
        submitter_name="Bob",
        submitter_email="bob@co.com",
        approver_email="sarah.finance@company.com",
        amount=Decimal("1250.00"),
        description="Software subscription",
        submitted_at=utc_now() - timedelta(seconds=12),
        last_nudged_at=utc_now() - timedelta(seconds=2) # escalation threshold is 5s in test env
    )
    repo.save_report(report)
    actions = engine.run_tick("tick_3")
    assert len(actions) == 0
    assert repo.get_report("EXP-102").status == ReportStatus.NUDGED

def test_scenario_4_nudged_past_escalation_threshold(setup_engine):
    engine, repo, worker, _ = setup_engine
    report = ExpenseReport(
        report_id="EXP-103",
        status=ReportStatus.NUDGED,
        submitter_name="Carlos",
        submitter_email="carlos@co.com",
        approver_email="sarah.finance@company.com",
        backup_approver_email="marcus.director@company.com",
        amount=Decimal("3400.00"),
        description="Conference venue",
        submitted_at=utc_now() - timedelta(seconds=20),
        last_nudged_at=utc_now() - timedelta(seconds=10)
    )
    repo.save_report(report)
    actions = engine.run_tick("tick_4")
    assert len(actions) == 1
    action = actions[0]
    assert action.status == ActionStatus.COMPLETED
    assert action.state_transition == StateTransitionResult.APPLIED
    assert action.recipient == "marcus.director@company.com"
    assert repo.get_report("EXP-103").status == ReportStatus.ESCALATED

def test_scenario_5_resolved_report_is_inert(setup_engine):
    engine, repo, worker, _ = setup_engine
    report = ExpenseReport(
        report_id="EXP-104",
        status=ReportStatus.RESOLVED,
        submitter_name="Diana",
        submitter_email="diana@co.com",
        approver_email="sarah.finance@company.com",
        amount=Decimal("520.00"),
        description="Ergonomic equipment",
        submitted_at=utc_now() - timedelta(seconds=100)
    )
    repo.save_report(report)
    actions = engine.run_tick("tick_5")
    assert len(actions) == 0
    assert repo.get_report("EXP-104").status == ReportStatus.RESOLVED

def test_scenario_11_no_backup_approver_falls_back_to_admin(setup_engine):
    engine, repo, worker, registry = setup_engine
    report = ExpenseReport(
        report_id="EXP-105",
        status=ReportStatus.NUDGED,
        submitter_name="Evan",
        submitter_email="evan@co.com",
        approver_email="approver_without_backup@company.com",
        backup_approver_email=None,
        amount=Decimal("890.00"),
        description="Emergency travel",
        submitted_at=utc_now() - timedelta(seconds=30),
        last_nudged_at=utc_now() - timedelta(seconds=10)
    )
    registry.register_approver("approver_without_backup@company.com", None)
    repo.save_report(report)
    actions = engine.run_tick("tick_11")
    assert len(actions) == 1
    action = actions[0]
    assert action.recipient == "admin-escalations@company.com"
    assert action.status == ActionStatus.COMPLETED

def test_scenario_12_notification_worker_failure_and_retry(setup_engine):
    engine, repo, worker, _ = setup_engine
    report = ExpenseReport(
        report_id="EXP-112",
        status=ReportStatus.PENDING,
        submitter_name="Fiona",
        submitter_email="fiona@co.com",
        approver_email="sarah.finance@company.com",
        amount=Decimal("600.00"),
        description="Lab equipment",
        submitted_at=utc_now() - timedelta(seconds=10)
    )
    repo.save_report(report)

    # 1. Simulate worker delivery failure
    worker.simulate_failure = True
    actions1 = engine.run_tick("tick_fail")
    assert len(actions1) == 1
    act1 = actions1[0]
    assert act1.status == ActionStatus.FAILED
    assert repo.get_report("EXP-112").status == ReportStatus.PENDING  # State untouched

    # 2. Worker recovers, tick retries same logical action
    worker.simulate_failure = False
    # Clear backoff time for immediate test execution
    act1.next_attempt_at = utc_now() - timedelta(seconds=1)
    repo.save_action(act1)

    actions2 = engine.run_tick("tick_retry")
    assert len(actions2) == 1
    act2 = actions2[0]
    assert act2.status == ActionStatus.COMPLETED
    assert act2.state_transition == StateTransitionResult.APPLIED
    assert repo.get_report("EXP-112").status == ReportStatus.NUDGED
