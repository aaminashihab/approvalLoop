from datetime import timedelta
from decimal import Decimal
from approval_loop.domain.models import ExpenseReport, ReportStatus, ActionType, utc_now
from approval_loop.domain.eligibility import EligibilityEvaluator
from approval_loop.config import ThresholdConfig

def test_fresh_report_not_eligible():
    now = utc_now()
    thresholds = ThresholdConfig(nudge_threshold_seconds=10, escalation_threshold_seconds=30, scheduler_frequency_seconds=5)
    report = ExpenseReport(
        report_id="EXP-1",
        submitter_name="A",
        submitter_email="a@co.com",
        approver_email="app@co.com",
        amount=Decimal("100.00"),
        description="Lunch",
        submitted_at=now - timedelta(seconds=2)
    )
    res = EligibilityEvaluator.evaluate(report, now, thresholds)
    assert res is None

def test_pending_report_due_for_nudge():
    now = utc_now()
    thresholds = ThresholdConfig(nudge_threshold_seconds=10, escalation_threshold_seconds=30, scheduler_frequency_seconds=5)
    report = ExpenseReport(
        report_id="EXP-2",
        submitter_name="A",
        submitter_email="a@co.com",
        approver_email="app@co.com",
        amount=Decimal("100.00"),
        description="Lunch",
        submitted_at=now - timedelta(seconds=15)
    )
    res = EligibilityEvaluator.evaluate(report, now, thresholds)
    assert res == (ActionType.NUDGE, ReportStatus.NUDGED)

def test_nudged_report_due_for_escalation():
    now = utc_now()
    thresholds = ThresholdConfig(nudge_threshold_seconds=10, escalation_threshold_seconds=30, scheduler_frequency_seconds=5)
    report = ExpenseReport(
        report_id="EXP-3",
        status=ReportStatus.NUDGED,
        submitter_name="A",
        submitter_email="a@co.com",
        approver_email="app@co.com",
        amount=Decimal("100.00"),
        description="Lunch",
        submitted_at=now - timedelta(seconds=50),
        last_nudged_at=now - timedelta(seconds=35)
    )
    res = EligibilityEvaluator.evaluate(report, now, thresholds)
    assert res == (ActionType.ESCALATE, ReportStatus.ESCALATED)

def test_resolved_report_never_eligible():
    now = utc_now()
    thresholds = ThresholdConfig(nudge_threshold_seconds=10, escalation_threshold_seconds=30, scheduler_frequency_seconds=5)
    report = ExpenseReport(
        report_id="EXP-4",
        status=ReportStatus.RESOLVED,
        submitter_name="A",
        submitter_email="a@co.com",
        approver_email="app@co.com",
        amount=Decimal("100.00"),
        description="Lunch",
        submitted_at=now - timedelta(seconds=100)
    )
    res = EligibilityEvaluator.evaluate(report, now, thresholds)
    assert res is None
