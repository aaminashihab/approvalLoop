from decimal import Decimal
from approval_loop.domain.models import (
    ExpenseReport, ActionRecord, ActionType, ReportStatus, ActionStatus
)
from approval_loop.storage.memory_repo import InMemoryRepository

def test_scenario_10_concurrent_claims_idempotency():
    repo = InMemoryRepository()
    report = ExpenseReport(
        report_id="EXP-104",
        status=ReportStatus.PENDING,
        submitter_name="Alice",
        submitter_email="alice@co.com",
        approver_email="app@co.com",
        amount=Decimal("500.00"),
        description="Monitor"
    )
    repo.save_report(report)

    action1 = ActionRecord(
        report_id="EXP-104",
        action_type=ActionType.NUDGE,
        source_state=ReportStatus.PENDING,
        target_state=ReportStatus.NUDGED,
        tick_id="tick_A",
        idempotency_key="EXP-104:nudge",
        recipient="app@co.com",
        amount=Decimal("500.00")
    )

    action2 = ActionRecord(
        report_id="EXP-104",
        action_type=ActionType.NUDGE,
        source_state=ReportStatus.PENDING,
        target_state=ReportStatus.NUDGED,
        tick_id="tick_B",
        idempotency_key="EXP-104:nudge",
        recipient="app@co.com",
        amount=Decimal("500.00")
    )

    # First tick claim succeeds
    claimed1, msg1, act1 = repo.claim_action_transaction(action1)
    assert claimed1 is True
    assert act1.status == ActionStatus.PROCESSING

    # Concurrent second tick claim is rejected
    claimed2, msg2, act2 = repo.claim_action_transaction(action2)
    assert claimed2 is False
    assert "in-flight" in msg2 or "already" in msg2
