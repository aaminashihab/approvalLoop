from abc import ABC, abstractmethod
from approval_loop.domain.models import ExpenseReport, ActionRecord

class BaseRepository(ABC):
    @abstractmethod
    def get_report(self, report_id: str) -> ExpenseReport | None:
        pass

    @abstractmethod
    def list_open_reports(self) -> list[ExpenseReport]:
        pass

    @abstractmethod
    def list_all_reports(self) -> list[ExpenseReport]:
        pass

    @abstractmethod
    def save_report(self, report: ExpenseReport):
        pass

    @abstractmethod
    def resolve_report(self, report_id: str) -> ExpenseReport | None:
        pass

    @abstractmethod
    def claim_action_transaction(self, action: ActionRecord) -> tuple[bool, str, ActionRecord | None]:
        """
        Atomically checks eligibility and claims logical action {report_id}:{action_type}.
        Returns (success: bool, reason: str, active_action: ActionRecord | None).
        """
        pass

    @abstractmethod
    def mark_failed(self, action_id: str, error_msg: str, backoff_seconds: int = 10) -> ActionRecord:
        pass

    @abstractmethod
    def save_action(self, action: ActionRecord):
        pass

    @abstractmethod
    def get_action(self, action_id: str) -> ActionRecord | None:
        pass

    @abstractmethod
    def list_all_actions(self) -> list[ActionRecord]:
        pass

    @abstractmethod
    def apply_conditional_transition(self, action_id: str) -> ActionRecord:
        """
        Mandatory conditional state transition (Invariant Section 5):
        Only applies target_state if report.status == action.source_state.
        Otherwise records state_transition = skipped and preserves current report state.
        """
        pass
