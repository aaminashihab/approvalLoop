from decimal import Decimal
from approval_loop.domain.models import (
    ExpenseReport, ActionRecord, ActionType, ReportStatus,
    ValidatorResultEnum, NotificationEnvelope
)
from approval_loop.domain.registry import ApproverRegistry
from approval_loop.validator.validator import DeterministicValidator

def setup_validator():
    registry = ApproverRegistry(admin_fallback_email="admin@company.com")
    registry.register_approver("approver1@co.com", "backup1@co.com")
    return DeterministicValidator(registry)

def test_validator_pass():
    val = setup_validator()
    report = ExpenseReport(
        report_id="EXP-101",
        submitter_name="Alice",
        submitter_email="alice@co.com",
        approver_email="approver1@co.com",
        amount=Decimal("250.00"),
        description="Software license"
    )
    action = ActionRecord(
        report_id="EXP-101",
        action_type=ActionType.NUDGE,
        source_state=ReportStatus.PENDING,
        target_state=ReportStatus.NUDGED,
        tick_id="t1",
        idempotency_key="EXP-101:nudge",
        recipient="approver1@co.com",
        amount=Decimal("250.00")
    )
    envelope = NotificationEnvelope(
        report_id="EXP-101",
        amount=Decimal("250.00"),
        currency="USD",
        recipient="approver1@co.com",
        submitter_name="Alice",
        subject="Action Required",
        body_text="Please review EXP-101"
    )
    res, reason, checks = val.validate(action, report, envelope)
    assert res == ValidatorResultEnum.PASS
    assert checks.recipient_verified is True
    assert checks.amount_verified is True
    assert checks.report_id_verified is True
    assert checks.state_verified is True

def test_scenario_6_wrong_recipient_blocked():
    val = setup_validator()
    report = ExpenseReport(
        report_id="EXP-101",
        submitter_name="Alice",
        submitter_email="alice@co.com",
        approver_email="approver1@co.com",
        amount=Decimal("250.00"),
        description="Software license"
    )
    action = ActionRecord(
        report_id="EXP-101",
        action_type=ActionType.NUDGE,
        source_state=ReportStatus.PENDING,
        target_state=ReportStatus.NUDGED,
        tick_id="t1",
        idempotency_key="EXP-101:nudge",
        recipient="intruder@external.com",
        amount=Decimal("250.00")
    )
    envelope = NotificationEnvelope(
        report_id="EXP-101",
        amount=Decimal("250.00"),
        currency="USD",
        recipient="intruder@external.com",
        submitter_name="Alice",
        subject="Action Required",
        body_text="Please review EXP-101"
    )
    res, reason, checks = val.validate(action, report, envelope)
    assert res == ValidatorResultEnum.BLOCKED
    assert checks.recipient_verified is False
    assert "not authorized in approver registry" in reason

def test_scenario_7_wrong_amount_blocked():
    val = setup_validator()
    report = ExpenseReport(
        report_id="EXP-101",
        submitter_name="Alice",
        submitter_email="alice@co.com",
        approver_email="approver1@co.com",
        amount=Decimal("250.00"),
        description="Software license"
    )
    action = ActionRecord(
        report_id="EXP-101",
        action_type=ActionType.NUDGE,
        source_state=ReportStatus.PENDING,
        target_state=ReportStatus.NUDGED,
        tick_id="t1",
        idempotency_key="EXP-101:nudge",
        recipient="approver1@co.com",
        amount=Decimal("250.00")
    )
    envelope = NotificationEnvelope(
        report_id="EXP-101",
        amount=Decimal("9999.00"),  # Hallucinated amount
        currency="USD",
        recipient="approver1@co.com",
        submitter_name="Alice",
        subject="Action Required",
        body_text="Please review EXP-101"
    )
    res, reason, checks = val.validate(action, report, envelope)
    assert res == ValidatorResultEnum.BLOCKED
    assert checks.amount_verified is False
    assert "Amount mismatch" in reason

def test_scenario_8_wrong_report_id_blocked():
    val = setup_validator()
    report = ExpenseReport(
        report_id="EXP-101",
        submitter_name="Alice",
        submitter_email="alice@co.com",
        approver_email="approver1@co.com",
        amount=Decimal("250.00"),
        description="Software license"
    )
    action = ActionRecord(
        report_id="EXP-101",
        action_type=ActionType.NUDGE,
        source_state=ReportStatus.PENDING,
        target_state=ReportStatus.NUDGED,
        tick_id="t1",
        idempotency_key="EXP-101:nudge",
        recipient="approver1@co.com",
        amount=Decimal("250.00")
    )
    envelope = NotificationEnvelope(
        report_id="EXP-FAKE-999",  # Hallucinated ID
        amount=Decimal("250.00"),
        currency="USD",
        recipient="approver1@co.com",
        submitter_name="Alice",
        subject="Action Required",
        body_text="Please review EXP-101"
    )
    res, reason, checks = val.validate(action, report, envelope)
    assert res == ValidatorResultEnum.BLOCKED
    assert checks.report_id_verified is False
    assert "Report ID mismatch" in reason

def test_scenario_9_illegal_transition_blocked():
    val = setup_validator()
    report = ExpenseReport(
        report_id="EXP-101",
        status=ReportStatus.RESOLVED,
        submitter_name="Alice",
        submitter_email="alice@co.com",
        approver_email="approver1@co.com",
        amount=Decimal("250.00"),
        description="Software license"
    )
    action = ActionRecord(
        report_id="EXP-101",
        action_type=ActionType.NUDGE,
        source_state=ReportStatus.RESOLVED,
        target_state=ReportStatus.NUDGED,  # Illegal
        tick_id="t1",
        idempotency_key="EXP-101:nudge",
        recipient="approver1@co.com",
        amount=Decimal("250.00")
    )
    envelope = NotificationEnvelope(
        report_id="EXP-101",
        amount=Decimal("250.00"),
        currency="USD",
        recipient="approver1@co.com",
        submitter_name="Alice",
        subject="Action Required",
        body_text="Please review EXP-101"
    )
    res, reason, checks = val.validate(action, report, envelope)
    assert res == ValidatorResultEnum.BLOCKED
    assert checks.state_verified is False
    assert "Illegal state transition" in reason
