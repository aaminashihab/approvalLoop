from approval_loop.domain.models import ReportStatus, ActionType

LEGAL_TRANSITIONS = {
    (ReportStatus.PENDING, ActionType.NUDGE): ReportStatus.NUDGED,
    (ReportStatus.NUDGED, ActionType.ESCALATE): ReportStatus.ESCALATED,
}

class StateMachine:
    @staticmethod
    def get_target_state(current_state: ReportStatus, action_type: ActionType) -> ReportStatus | None:
        return LEGAL_TRANSITIONS.get((current_state, action_type))

    @staticmethod
    def is_transition_legal(current_state: ReportStatus, target_state: ReportStatus) -> bool:
        if current_state == ReportStatus.RESOLVED:
            return False  # Terminal state
        if current_state == ReportStatus.PENDING and target_state in (ReportStatus.NUDGED, ReportStatus.RESOLVED):
            return True
        if current_state == ReportStatus.NUDGED and target_state in (ReportStatus.ESCALATED, ReportStatus.RESOLVED):
            return True
        if current_state == ReportStatus.ESCALATED and target_state == ReportStatus.RESOLVED:
            return True
        return False
