from decimal import Decimal
from approval_loop.domain.models import (
    ExpenseReport, ActionRecord, ActionType, ReportStatus, NotificationEnvelope
)
from approval_loop.config import Settings, AppEnvironment
from approval_loop.policy.policy_engine import PolicyEngine, PolicyDecisionEnum

def test_policy_allow_standard_nudge():
    policy = PolicyEngine()
    report = ExpenseReport(
        report_id="EXP-101",
        submitter_name="Alice",
        submitter_email="alice@company.com",
        approver_email="sarah.finance@company.com",
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
        recipient="sarah.finance@company.com",
        amount=Decimal("250.00")
    )
    envelope = NotificationEnvelope(
        report_id="EXP-101",
        amount=Decimal("250.00"),
        currency="USD",
        recipient="sarah.finance@company.com",
        submitter_name="Alice",
        subject="Action Required",
        body_text="Please review"
    )
    res, reason = policy.evaluate(action, report, envelope)
    assert res == PolicyDecisionEnum.ALLOW
    assert "Policy Authorization Granted" in reason

def test_policy_deny_restricted_domain():
    policy = PolicyEngine()
    report = ExpenseReport(
        report_id="EXP-102",
        submitter_name="Bob",
        submitter_email="bob@company.com",
        approver_email="sarah.finance@company.com",
        amount=Decimal("500.00"),
        description="Supplies"
    )
    action = ActionRecord(
        report_id="EXP-102",
        action_type=ActionType.NUDGE,
        source_state=ReportStatus.PENDING,
        target_state=ReportStatus.NUDGED,
        tick_id="t1",
        idempotency_key="EXP-102:nudge",
        recipient="intruder@external-attacker.com",
        amount=Decimal("500.00")
    )
    envelope = NotificationEnvelope(
        report_id="EXP-102",
        amount=Decimal("500.00"),
        currency="USD",
        recipient="intruder@external-attacker.com",
        submitter_name="Bob",
        subject="Action Required",
        body_text="Please review"
    )
    res, reason = policy.evaluate(action, report, envelope)
    assert res == PolicyDecisionEnum.DENY
    assert "POL-DOM-01" in reason

def test_policy_deny_high_value_escalation_without_director_or_admin():
    policy = PolicyEngine()
    report = ExpenseReport(
        report_id="EXP-103",
        submitter_name="Carlos",
        submitter_email="carlos@company.com",
        approver_email="sarah.finance@company.com",
        amount=Decimal("7500.00"),  # > $5,000 threshold
        description="Enterprise servers"
    )
    action = ActionRecord(
        report_id="EXP-103",
        action_type=ActionType.ESCALATE,
        source_state=ReportStatus.NUDGED,
        target_state=ReportStatus.ESCALATED,
        tick_id="t1",
        idempotency_key="EXP-103:escalate",
        recipient="junior.peer@company.com",  # Not director/admin
        amount=Decimal("7500.00")
    )
    envelope = NotificationEnvelope(
        report_id="EXP-103",
        amount=Decimal("7500.00"),
        currency="USD",
        recipient="junior.peer@company.com",
        submitter_name="Carlos",
        subject="ESCALATION",
        body_text="High value escalation"
    )
    res, reason = policy.evaluate(action, report, envelope)
    assert res == PolicyDecisionEnum.DENY
    assert "POL-VAL-02" in reason

def test_policy_deny_resolved_report_action():
    policy = PolicyEngine()
    report = ExpenseReport(
        report_id="EXP-104",
        status=ReportStatus.RESOLVED,
        submitter_name="Diana",
        submitter_email="diana@company.com",
        approver_email="sarah.finance@company.com",
        amount=Decimal("100.00"),
        description="Lunch"
    )
    action = ActionRecord(
        report_id="EXP-104",
        action_type=ActionType.NUDGE,
        source_state=ReportStatus.RESOLVED,
        target_state=ReportStatus.NUDGED,
        tick_id="t1",
        idempotency_key="EXP-104:nudge",
        recipient="sarah.finance@company.com",
        amount=Decimal("100.00")
    )
    envelope = NotificationEnvelope(
        report_id="EXP-104",
        amount=Decimal("100.00"),
        currency="USD",
        recipient="sarah.finance@company.com",
        submitter_name="Diana",
        subject="Action Required",
        body_text="Please review"
    )
    res, reason = policy.evaluate(action, report, envelope)
    assert res == PolicyDecisionEnum.DENY
    assert "POL-STA-03" in reason
