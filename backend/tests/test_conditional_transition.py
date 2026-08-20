from decimal import Decimal
from approval_loop.domain.models import (
    ExpenseReport, ActionRecord, ActionType, ReportStatus, ActionStatus, StateTransitionResult
)
from approval_loop.storage.memory_repo import InMemoryRepository

def test_scenario_13_race_condition_guard():
    repo = InMemoryRepository()
    report = ExpenseReport(
        report_id="EXP-113",
        status=ReportStatus.PENDING,
        submitter_name="Charlie",
        submitter_email="charlie@co.com",
        approver_email="app@co.com",
        amount=Decimal("1200.00"),
        description="Server"
    )
    repo.save_report(report)

    action = ActionRecord(
        report_id="EXP-113",
        action_type=ActionType.NUDGE,
        source_state=ReportStatus.PENDING,
        target_state=ReportStatus.NUDGED,
        tick_id="tick_13",
        idempotency_key="EXP-113:nudge",
        recipient="app@co.com",
        amount=Decimal("1200.00")
    )

    # 1. Claim succeeds
    claimed, _, act = repo.claim_action_transaction(action)
    assert claimed is True

    # 2. Approver resolves the report while notification is sending
    repo.resolve_report("EXP-113")
    assert repo.get_report("EXP-113").status == ReportStatus.RESOLVED

    # 3. Worker completes delivery and attempts state transition
    completed_action = repo.apply_conditional_transition(act.action_id)

    # Invariant assertions: All 4 must strictly hold
    assert repo.get_report("EXP-113").status == ReportStatus.RESOLVED
    assert completed_action.status == ActionStatus.COMPLETED
    assert completed_action.state_transition == StateTransitionResult.SKIPPED
    assert completed_action.skip_reason == "report state changed before transition commit (expected=Pending, found=Resolved)"
