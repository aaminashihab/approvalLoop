import threading
from datetime import timedelta
from typing import Optional, Any
from approval_loop.storage.base import BaseRepository
from approval_loop.domain.models import (
    ExpenseReport, ActionRecord, ReportStatus, ActionStatus,
    StateTransitionResult, utc_now
)

class InMemoryRepository(BaseRepository):
    def __init__(self):
        self.reports: dict[str, ExpenseReport] = {}
        self.actions: dict[str, ActionRecord] = {}
        self.active_claims: dict[str, str] = {}  # idempotency_key -> action_id
        self.agents: dict[str, Any] = {}
        self.workflow_memories: dict[str, Any] = {}
        self.async_tasks: dict[str, Any] = {}
        self.async_idempotency_index: dict[str, str] = {}
        self._lock = threading.Lock()

    def get_report(self, report_id: str) -> ExpenseReport | None:
        with self._lock:
            return self.reports.get(report_id)

    def list_open_reports(self) -> list[ExpenseReport]:
        with self._lock:
            return [r for r in self.reports.values() if r.status != ReportStatus.RESOLVED]

    def list_all_reports(self) -> list[ExpenseReport]:
        with self._lock:
            return list(self.reports.values())

    def save_report(self, report: ExpenseReport):
        with self._lock:
            self.reports[report.report_id] = report

    def resolve_report(self, report_id: str) -> ExpenseReport | None:
        with self._lock:
            report = self.reports.get(report_id)
            if report:
                report.status = ReportStatus.RESOLVED
                report.resolved_at = utc_now()
            return report

    def claim_action_transaction(self, action: ActionRecord) -> tuple[bool, str, ActionRecord | None]:
        with self._lock:
            report = self.reports.get(action.report_id)
            if not report:
                return False, f"Report {action.report_id} not found", None

            if report.status != action.source_state:
                return False, f"Report state changed (expected {action.source_state.value}, found {report.status.value})", None

            now = utc_now()
            existing_action_id = self.active_claims.get(action.idempotency_key)
            if existing_action_id:
                existing_action = self.actions[existing_action_id]
                
                # Terminal states: COMPLETED or BLOCKED cannot be re-claimed
                if existing_action.status in (ActionStatus.COMPLETED, ActionStatus.SENT):
                    return False, f"Action {action.idempotency_key} already completed", None
                if existing_action.status == ActionStatus.BLOCKED:
                    return False, f"Action {action.idempotency_key} was terminally BLOCKED by validator", None

                # In-flight lease check (60s lease)
                if existing_action.status in (ActionStatus.CLAIMED, ActionStatus.PROCESSING):
                    if existing_action.claimed_at and (now - existing_action.claimed_at) < timedelta(seconds=60):
                        return False, f"Action {action.idempotency_key} is currently in-flight", None

                # Retryable operational failure
                if existing_action.status == ActionStatus.FAILED:
                    if existing_action.attempt_count >= existing_action.max_attempts:
                        return False, f"Action {action.idempotency_key} exceeded max_attempts ({existing_action.max_attempts})", None
                    if existing_action.next_attempt_at and now < existing_action.next_attempt_at:
                        return False, f"Action {action.idempotency_key} retry backoff not elapsed yet", None
                    
                    existing_action.status = ActionStatus.PROCESSING
                    existing_action.claimed_at = now
                    return True, "Retry claim acquired", existing_action

            # New initial claim
            action.claimed_at = now
            action.status = ActionStatus.PROCESSING
            self.active_claims[action.idempotency_key] = action.action_id
            self.actions[action.action_id] = action
            return True, "Claim committed", action

    def mark_failed(self, action_id: str, error_msg: str, backoff_seconds: int = 10) -> ActionRecord:
        with self._lock:
            action = self.actions[action_id]
            action.status = ActionStatus.FAILED
            action.attempt_count += 1
            action.last_error = error_msg
            action.next_attempt_at = utc_now() + timedelta(seconds=backoff_seconds * (2 ** (action.attempt_count - 1)))
            return action

    def save_action(self, action: ActionRecord):
        with self._lock:
            self.actions[action.action_id] = action

    def get_action(self, action_id: str) -> ActionRecord | None:
        with self._lock:
            return self.actions.get(action_id)

    def list_all_actions(self) -> list[ActionRecord]:
        with self._lock:
            # Sort newest first
            return sorted(self.actions.values(), key=lambda a: a.created_at, reverse=True)

    def apply_conditional_transition(self, action_id: str) -> ActionRecord:
        with self._lock:
            action = self.actions[action_id]
            report = self.reports[action.report_id]
            
            # RACE GUARD (Invariant from Section 5)
            if report.status == action.source_state:
                report.status = action.target_state
                if action.target_state == ReportStatus.NUDGED:
                    report.last_nudged_at = utc_now()
                elif action.target_state == ReportStatus.ESCALATED:
                    report.escalated_at = utc_now()
                
                action.state_transition = StateTransitionResult.APPLIED
                action.status = ActionStatus.COMPLETED
            else:
                action.state_transition = StateTransitionResult.SKIPPED
                action.skip_reason = f"report state changed before transition commit (expected={action.source_state.value}, found={report.status.value})"
                action.status = ActionStatus.COMPLETED

            action.completed_at = utc_now()
            return action

    # Agent Registry Operations
    def save_agent_registration(self, agent: Any):
        with self._lock:
            self.agents[agent.agent_id] = agent

    def get_agent_registration(self, agent_id: str) -> Any | None:
        with self._lock:
            return self.agents.get(agent_id)

    def list_agent_registrations(self) -> list[Any]:
        with self._lock:
            return list(self.agents.values())

    # Memory Bank Operations
    def save_workflow_memory(self, record: Any):
        with self._lock:
            self.workflow_memories[record.workflow_id] = record

    def get_workflow_memory(self, workflow_id: str) -> Any | None:
        with self._lock:
            return self.workflow_memories.get(workflow_id)

    def list_workflow_memories(self, agent_id: Optional[str] = None, state: Optional[str] = None) -> list[Any]:
        with self._lock:
            records = list(self.workflow_memories.values())
            if agent_id:
                records = [r for r in records if getattr(r, "agent_id", None) == agent_id]
            if state:
                records = [r for r in records if getattr(getattr(r, "state", None), "value", str(getattr(r, "state", None))) == state]
            return records

    # Async Task Operations
    def save_async_task(self, task: Any):
        with self._lock:
            task_id = getattr(task, "task_id", None) or task.get("task_id")
            idempotency_key = getattr(task, "idempotency_key", None) or (task.get("idempotency_key") if isinstance(task, dict) else None)
            self.async_tasks[task_id] = task
            if idempotency_key:
                self.async_idempotency_index[idempotency_key] = task_id

    def get_async_task(self, task_id: str) -> Any | None:
        with self._lock:
            return self.async_tasks.get(task_id)

    def get_async_task_by_idempotency_key(self, idempotency_key: str) -> Any | None:
        with self._lock:
            task_id = self.async_idempotency_index.get(idempotency_key)
            if task_id:
                return self.async_tasks.get(task_id)
            return None

    def list_async_tasks(self, status: Optional[str] = None) -> list[Any]:
        with self._lock:
            tasks = list(self.async_tasks.values())
            if status:
                tasks = [t for t in tasks if getattr(t, "status", None) == status or (isinstance(t, dict) and t.get("status") == status)]
            return tasks

