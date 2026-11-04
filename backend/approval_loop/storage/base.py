from abc import ABC, abstractmethod
from typing import Optional, Any
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

    # Agent registry, Memory Bank and async task storage. These are abstract on purpose: a silent no-op
    # default once let a backend "store" workflows that could never be listed again.
    # Agent Registry Extensions
    @abstractmethod
    def save_agent_registration(self, agent: Any):
        pass

    @abstractmethod
    def get_agent_registration(self, agent_id: str) -> Any | None:
        pass

    @abstractmethod
    def list_agent_registrations(self) -> list[Any]:
        pass

    # Memory Bank Extensions
    @abstractmethod
    def save_workflow_memory(self, record: Any):
        pass

    @abstractmethod
    def get_workflow_memory(self, workflow_id: str) -> Any | None:
        pass

    @abstractmethod
    def list_workflow_memories(self, agent_id: Optional[str] = None, state: Optional[str] = None) -> list[Any]:
        pass

    @abstractmethod
    def find_workflow_memory_by_action_id(self, action_id: str) -> Any | None:
        """Indexed lookup of the workflow that owns a pending/decided action (no full scan)."""
        pass

    @abstractmethod
    def compare_and_set_workflow_memory(self, record: Any, expected_state: str) -> bool:
        """
        Atomically stores `record` only if the stored workflow is still in `expected_state`.
        Returns False (and writes nothing) if another caller changed it first. This is what
        makes a human approval single-winner across processes, not just within one.
        """
        pass

    # Async Task Storage Extensions
    @abstractmethod
    def save_async_task(self, task: Any):
        pass

    @abstractmethod
    def get_async_task(self, task_id: str) -> Any | None:
        pass

    @abstractmethod
    def get_async_task_by_idempotency_key(self, idempotency_key: str) -> Any | None:
        pass

    @abstractmethod
    def list_async_tasks(self, status: Optional[str] = None) -> list[Any]:
        pass

