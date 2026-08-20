from datetime import datetime
from approval_loop.domain.models import ExpenseReport, ReportStatus, ActionType
from approval_loop.config import ThresholdConfig

class EligibilityEvaluator:
    """Pure deterministic eligibility evaluation — LLM never determines staleness."""
    @staticmethod
    def evaluate(report: ExpenseReport, current_time: datetime, thresholds: ThresholdConfig) -> tuple[ActionType, ReportStatus] | None:
        if report.status == ReportStatus.RESOLVED:
            return None

        if report.status == ReportStatus.PENDING:
            elapsed = (current_time - report.submitted_at).total_seconds()
            if elapsed >= thresholds.nudge_threshold_seconds:
                return (ActionType.NUDGE, ReportStatus.NUDGED)

        elif report.status == ReportStatus.NUDGED and report.last_nudged_at:
            elapsed = (current_time - report.last_nudged_at).total_seconds()
            if elapsed >= thresholds.escalation_threshold_seconds:
                return (ActionType.ESCALATE, ReportStatus.ESCALATED)

        return None
