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

def test_1000_reports_deterministic_scale_simulation():
    """
    Large-Scale Deterministic Simulation:
    Processes 1,000 synthetic approval reports across multiple scheduler ticks,
    verifying 0 duplicate actions, 0 invalid transitions, 0 unauthorized sends, and 0 race regressions.
    """
    repo = InMemoryRepository()
    settings = Settings(app_env=AppEnvironment.TEST)
    registry = ApproverRegistry(admin_fallback_email="admin@company.com")
    
    for i in range(50):
        registry.register_approver(f"approver_{i}@company.com", f"backup_{i}@company.com")

    validator = DeterministicValidator(registry=registry)
    drafter = GeminiAgentDrafter()
    worker = MockNotificationWorker()
    engine = ApprovalEngine(repo, settings, registry, drafter, validator, worker)

    now = utc_now()
    total_created = 1000

    # 1. Seed 1,000 Synthetic Reports
    for idx in range(total_created):
        approver_idx = idx % 50

        if idx < 300:
            # Fresh Pending (<2s) -> observed, untouched
            r = ExpenseReport(
                report_id=f"EXP-{idx:04d}",
                status=ReportStatus.PENDING,
                submitter_name=f"Submitter {idx}",
                submitter_email=f"sub_{idx}@company.com",
                approver_email=f"approver_{approver_idx}@company.com",
                backup_approver_email=f"backup_{approver_idx}@company.com",
                amount=Decimal(f"{100 + idx}.50"),
                description=f"Expense report {idx}",
                submitted_at=now
            )
        elif idx < 600:
            # Stale Pending (>2s) -> due for nudge
            r = ExpenseReport(
                report_id=f"EXP-{idx:04d}",
                status=ReportStatus.PENDING,
                submitter_name=f"Submitter {idx}",
                submitter_email=f"sub_{idx}@company.com",
                approver_email=f"approver_{approver_idx}@company.com",
                backup_approver_email=f"backup_{approver_idx}@company.com",
                amount=Decimal(f"{100 + idx}.50"),
                description=f"Expense report {idx}",
                submitted_at=now - timedelta(seconds=10)
            )
        elif idx < 800:
            # Stale Nudged (>5s) -> due for escalation
            r = ExpenseReport(
                report_id=f"EXP-{idx:04d}",
                status=ReportStatus.NUDGED,
                submitter_name=f"Submitter {idx}",
                submitter_email=f"sub_{idx}@company.com",
                approver_email=f"approver_{approver_idx}@company.com",
                backup_approver_email=f"backup_{approver_idx}@company.com",
                amount=Decimal(f"{100 + idx}.50"),
                description=f"Expense report {idx}",
                submitted_at=now - timedelta(seconds=30),
                last_nudged_at=now - timedelta(seconds=15)
            )
        elif idx < 900:
            # Resolved -> completely inert
            r = ExpenseReport(
                report_id=f"EXP-{idx:04d}",
                status=ReportStatus.RESOLVED,
                submitter_name=f"Submitter {idx}",
                submitter_email=f"sub_{idx}@company.com",
                approver_email=f"approver_{approver_idx}@company.com",
                backup_approver_email=f"backup_{approver_idx}@company.com",
                amount=Decimal(f"{100 + idx}.50"),
                description=f"Expense report {idx}",
                submitted_at=now - timedelta(seconds=100),
                resolved_at=now - timedelta(seconds=50)
            )
        elif idx < 950:
            # Missing Backup Approver on approver without registered backup -> Admin Fallback test
            app_no_backup = f"approver_nobackup_{idx}@company.com"
            registry.register_approver(app_no_backup, None)
            r = ExpenseReport(
                report_id=f"EXP-{idx:04d}",
                status=ReportStatus.NUDGED,
                submitter_name=f"Submitter {idx}",
                submitter_email=f"sub_{idx}@company.com",
                approver_email=app_no_backup,
                backup_approver_email=None,
                amount=Decimal(f"{100 + idx}.50"),
                description=f"Expense report {idx}",
                submitted_at=now - timedelta(seconds=40),
                last_nudged_at=now - timedelta(seconds=20)
            )
        else:
            # Race Condition Candidates (Resolved right when nudge sent)
            r = ExpenseReport(
                report_id=f"EXP-{idx:04d}",
                status=ReportStatus.PENDING,
                submitter_name=f"Submitter {idx}",
                submitter_email=f"sub_{idx}@company.com",
                approver_email=f"approver_{approver_idx}@company.com",
                backup_approver_email=f"backup_{approver_idx}@company.com",
                amount=Decimal(f"{100 + idx}.50"),
                description=f"Expense report {idx}",
                submitted_at=now - timedelta(seconds=12)
            )

        repo.save_report(r)

    # Set callback for race condition reports (950..999)
    def _race_callback(envelope):
        rep_num = int(envelope.report_id.split("-")[1])
        if rep_num >= 950:
            repo.resolve_report(envelope.report_id)

    worker.on_send_callback = _race_callback

    # 2. RUN SCHEDULER TICK 1
    actions_tick1 = engine.run_tick("tick_sim_1")

    # 3. RUN SCHEDULER TICK 2 (Immediately after to test idempotency / dedup)
    actions_tick2 = engine.run_tick("tick_sim_2")

    # 4. Compute Invariant Metrics
    all_actions = repo.list_all_actions()
    all_reports = repo.list_all_reports()

    # Metric 1: Total Reports Processed
    assert len(all_reports) == 1000

    # Metric 2: Nudges executed (300 stale pending + 50 race pending = 350 nudge actions attempted)
    nudge_actions = [a for a in all_actions if a.action_type == ActionType.NUDGE]
    assert len(nudge_actions) == 350

    # Metric 3: Escalations executed (200 stale nudged + 50 missing backup = 250 escalation actions)
    escalate_actions = [a for a in all_actions if a.action_type == ActionType.ESCALATE]
    assert len(escalate_actions) == 250

    # Metric 4: Admin fallback count (50 missing backup escalated to admin)
    admin_escalations = [a for a in escalate_actions if a.recipient == "admin@company.com"]
    assert len(admin_escalations) == 50

    # Metric 5: Duplicate Successful Actions on Tick 2 MUST BE ZERO
    assert len(actions_tick2) == 0

    # Metric 6: Race-Condition Skips (50 reports resolved mid-flight)
    skipped_actions = [a for a in all_actions if a.state_transition == StateTransitionResult.SKIPPED]
    assert len(skipped_actions) == 50
    for sa in skipped_actions:
        assert repo.get_report(sa.report_id).status == ReportStatus.RESOLVED
        assert "report state changed before transition commit" in sa.skip_reason

    # Metric 7: Resolved reports untouched
    for idx in range(800, 900):
        assert repo.get_report(f"EXP-{idx:04d}").status == ReportStatus.RESOLVED
        assert not any(a.report_id == f"EXP-{idx:04d}" for a in all_actions)

    # Metric 8: Unauthorized sends MUST BE ZERO
    assert all(a.validator_result == ValidatorResultEnum.PASS for a in all_actions if a.status == ActionStatus.COMPLETED)

    # Metric 9: Human prompts required MUST BE ZERO
    metrics = engine.get_autonomy_metrics()
    assert metrics.human_prompts_required == 0
