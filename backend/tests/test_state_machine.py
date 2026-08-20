import pytest
from approval_loop.domain.models import ReportStatus, ActionType
from approval_loop.domain.state_machine import StateMachine

def test_legal_transitions():
    assert StateMachine.get_target_state(ReportStatus.PENDING, ActionType.NUDGE) == ReportStatus.NUDGED
    assert StateMachine.get_target_state(ReportStatus.NUDGED, ActionType.ESCALATE) == ReportStatus.ESCALATED
    assert StateMachine.is_transition_legal(ReportStatus.PENDING, ReportStatus.NUDGED) is True
    assert StateMachine.is_transition_legal(ReportStatus.NUDGED, ReportStatus.ESCALATED) is True
    assert StateMachine.is_transition_legal(ReportStatus.PENDING, ReportStatus.RESOLVED) is True
    assert StateMachine.is_transition_legal(ReportStatus.NUDGED, ReportStatus.RESOLVED) is True
    assert StateMachine.is_transition_legal(ReportStatus.ESCALATED, ReportStatus.RESOLVED) is True

def test_illegal_transitions():
    # Resolved is terminal
    assert StateMachine.is_transition_legal(ReportStatus.RESOLVED, ReportStatus.NUDGED) is False
    assert StateMachine.is_transition_legal(ReportStatus.RESOLVED, ReportStatus.ESCALATED) is False
    assert StateMachine.is_transition_legal(ReportStatus.RESOLVED, ReportStatus.PENDING) is False
    # Cannot jump backward
    assert StateMachine.is_transition_legal(ReportStatus.ESCALATED, ReportStatus.PENDING) is False
    assert StateMachine.is_transition_legal(ReportStatus.NUDGED, ReportStatus.PENDING) is False
