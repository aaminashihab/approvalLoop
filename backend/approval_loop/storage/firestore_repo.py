from datetime import timedelta
from typing import Optional, Any
from approval_loop.storage.base import BaseRepository
from approval_loop.domain.models import (
    ExpenseReport, ActionRecord, ReportStatus, ActionStatus,
    StateTransitionResult, utc_now
)
from google.cloud import firestore

class FirestoreRepository(BaseRepository):
    def __init__(
        self,
        project_id: str,
        reports_col: str = "expense_reports",
        actions_col: str = "approval_actions",
        agents_col: str = "agent_registry",
        memory_col: str = "workflow_memories",
        tasks_col: str = "async_tasks"
    ):
        self.client = firestore.Client(project=project_id)
        self.reports_col = reports_col
        self.actions_col = actions_col
        self.agents_col = agents_col
        self.memory_col = memory_col
        self.tasks_col = tasks_col

    def get_report(self, report_id: str) -> ExpenseReport | None:
        doc = self.client.collection(self.reports_col).document(report_id).get()
        if doc.exists:
            return ExpenseReport(**doc.to_dict())
        return None

    def list_open_reports(self) -> list[ExpenseReport]:
        docs = self.client.collection(self.reports_col).where("status", "!=", ReportStatus.RESOLVED.value).stream()
        return [ExpenseReport(**d.to_dict()) for d in docs]

    def list_all_reports(self) -> list[ExpenseReport]:
        docs = self.client.collection(self.reports_col).stream()
        return [ExpenseReport(**d.to_dict()) for d in docs]

    def save_report(self, report: ExpenseReport):
        self.client.collection(self.reports_col).document(report.report_id).set(report.to_dict())

    def resolve_report(self, report_id: str) -> ExpenseReport | None:
        ref = self.client.collection(self.reports_col).document(report_id)
        now = utc_now()
        ref.update({
            "status": ReportStatus.RESOLVED.value,
            "resolved_at": now.isoformat()
        })
        return self.get_report(report_id)

    def claim_action_transaction(self, action: ActionRecord) -> tuple[bool, str, ActionRecord | None]:
        transaction = self.client.transaction()
        report_ref = self.client.collection(self.reports_col).document(action.report_id)
        action_ref = self.client.collection(self.actions_col).document(action.action_id)
        claim_ref = self.client.collection("action_claims").document(action.idempotency_key)

        @firestore.transactional
        def _in_transaction(txn):
            report_snap = report_ref.get(transaction=txn)
            if not report_snap.exists:
                return False, f"Report {action.report_id} not found", None

            report_data = report_snap.to_dict()
            if report_data.get("status") != action.source_state.value:
                return False, f"Report state changed", None

            claim_snap = claim_ref.get(transaction=txn)
            now = utc_now()
            if claim_snap.exists:
                claim_data = claim_snap.to_dict()
                existing_action_id = claim_data.get("action_id")
                existing_snap = self.client.collection(self.actions_col).document(existing_action_id).get(transaction=txn)
                if existing_snap.exists:
                    existing_act = ActionRecord(**existing_snap.to_dict())
                    if existing_act.status in (ActionStatus.COMPLETED, ActionStatus.SENT, ActionStatus.BLOCKED):
                        return False, f"Action already processed/blocked", None
                    if existing_act.status == ActionStatus.FAILED:
                        if existing_act.attempt_count >= existing_act.max_attempts:
                            return False, "Exceeded max attempts", None
                        if existing_act.next_attempt_at and now < existing_act.next_attempt_at:
                            return False, "Backoff in effect", None
                        existing_act.status = ActionStatus.PROCESSING
                        existing_act.claimed_at = now
                        txn.set(self.client.collection(self.actions_col).document(existing_action_id), existing_act.to_dict())
                        return True, "Retry claim acquired", existing_act

            action.claimed_at = now
            action.status = ActionStatus.PROCESSING
            txn.set(claim_ref, {"action_id": action.action_id, "idempotency_key": action.idempotency_key, "created_at": now.isoformat()})
            txn.set(action_ref, action.to_dict())
            return True, "Claim committed", action

        return _in_transaction(transaction)

    def mark_failed(self, action_id: str, error_msg: str, backoff_seconds: int = 10) -> ActionRecord:
        ref = self.client.collection(self.actions_col).document(action_id)
        doc = ref.get()
        act = ActionRecord(**doc.to_dict())
        act.status = ActionStatus.FAILED
        act.attempt_count += 1
        act.last_error = error_msg
        act.next_attempt_at = utc_now() + timedelta(seconds=backoff_seconds * (2 ** (act.attempt_count - 1)))
        ref.set(act.to_dict())
        return act

    def save_action(self, action: ActionRecord):
        self.client.collection(self.actions_col).document(action.action_id).set(action.to_dict())

    def get_action(self, action_id: str) -> ActionRecord | None:
        doc = self.client.collection(self.actions_col).document(action_id).get()
        if doc.exists:
            return ActionRecord(**doc.to_dict())
        return None

    def list_all_actions(self) -> list[ActionRecord]:
        docs = self.client.collection(self.actions_col).order_by("created_at", direction=firestore.Query.DESCENDING).stream()
        return [ActionRecord(**d.to_dict()) for d in docs]

    def apply_conditional_transition(self, action_id: str) -> ActionRecord:
        transaction = self.client.transaction()
        action_ref = self.client.collection(self.actions_col).document(action_id)

        @firestore.transactional
        def _apply_in_tx(txn):
            action_doc = action_ref.get(transaction=txn)
            action = ActionRecord(**action_doc.to_dict())
            report_ref = self.client.collection(self.reports_col).document(action.report_id)
            report_doc = report_ref.get(transaction=txn)
            report = ExpenseReport(**report_doc.to_dict())

            now = utc_now()
            if report.status == action.source_state:
                report.status = action.target_state
                if action.target_state == ReportStatus.NUDGED:
                    report.last_nudged_at = now
                elif action.target_state == ReportStatus.ESCALATED:
                    report.escalated_at = now
                txn.set(report_ref, report.to_dict())
                action.state_transition = StateTransitionResult.APPLIED
                action.status = ActionStatus.COMPLETED
            else:
                action.state_transition = StateTransitionResult.SKIPPED
                action.skip_reason = f"report state changed before transition commit (expected={action.source_state.value}, found={report.status.value})"
                action.status = ActionStatus.COMPLETED

            action.completed_at = now
            txn.set(action_ref, action.to_dict())
            return action

        return _apply_in_tx(transaction)

    # Agent Registry Firestore Operations
    def save_agent_registration(self, agent: Any):
        data = agent.to_dict() if hasattr(agent, "to_dict") else agent.model_dump()
        self.client.collection(self.agents_col).document(agent.agent_id).set(data)

    def get_agent_registration(self, agent_id: str) -> Any | None:
        doc = self.client.collection(self.agents_col).document(agent_id).get()
        if doc.exists:
            from approval_loop.domain.agent_registry import AgentRegistration
            return AgentRegistration(**doc.to_dict())
        return None

    def list_agent_registrations(self) -> list[Any]:
        docs = self.client.collection(self.agents_col).stream()
        from approval_loop.domain.agent_registry import AgentRegistration
        return [AgentRegistration(**d.to_dict()) for d in docs]

    # Memory Bank Firestore Operations
    def save_workflow_memory(self, record: Any):
        data = record.to_dict() if hasattr(record, "to_dict") else record.model_dump()
        self.client.collection(self.memory_col).document(record.workflow_id).set(data)

    def get_workflow_memory(self, workflow_id: str) -> Any | None:
        doc = self.client.collection(self.memory_col).document(workflow_id).get()
        if doc.exists:
            from approval_loop.memory.memory_bank import WorkflowMemoryRecord
            return WorkflowMemoryRecord(**doc.to_dict())
        return None

    # Async Task Firestore Operations
    def save_async_task(self, task: Any):
        data = task.to_dict() if hasattr(task, "to_dict") else (task.model_dump() if hasattr(task, "model_dump") else task)
        task_id = data.get("task_id")
        self.client.collection(self.tasks_col).document(task_id).set(data)
        if data.get("idempotency_key"):
            self.client.collection("async_task_index").document(data["idempotency_key"]).set({"task_id": task_id})

    def get_async_task(self, task_id: str) -> Any | None:
        doc = self.client.collection(self.tasks_col).document(task_id).get()
        if doc.exists:
            from approval_loop.runtime.async_runtime import AsyncTaskRecord
            return AsyncTaskRecord(**doc.to_dict())
        return None

    def get_async_task_by_idempotency_key(self, idempotency_key: str) -> Any | None:
        idx_doc = self.client.collection("async_task_index").document(idempotency_key).get()
        if idx_doc.exists:
            task_id = idx_doc.to_dict().get("task_id")
            if task_id:
                return self.get_async_task(task_id)
        return None

    def list_async_tasks(self, status: Optional[str] = None) -> list[Any]:
        query = self.client.collection(self.tasks_col)
        if status:
            query = query.where("status", "==", status)
        docs = query.order_by("created_at", direction=firestore.Query.DESCENDING).limit(100).stream()
        from approval_loop.runtime.async_runtime import AsyncTaskRecord
        return [AsyncTaskRecord(**d.to_dict()) for d in docs]

    def claim_async_task_transaction(
        self,
        worker_id: str = "worker-1",
        lease_duration_seconds: int = 60
    ) -> Any | None:
        transaction = self.client.transaction()
        now = utc_now()

        @firestore.transactional
        def _claim_in_tx(txn):
            query = self.client.collection(self.tasks_col).where("status", "in", ["queued", "retry_pending"]).limit(20)
            docs = list(query.stream(transaction=txn))
            from approval_loop.runtime.async_runtime import AsyncTaskState, AsyncTaskRecord
            for doc in docs:
                data = doc.to_dict()
                rec = AsyncTaskRecord(**data)
                if rec.next_attempt_at and now < rec.next_attempt_at:
                    continue
                rec.status = AsyncTaskState.LEASED
                rec.claimed_at = now
                rec.worker_id = worker_id
                rec.lease_expires_at = now + timedelta(seconds=lease_duration_seconds)
                rec.attempt_count += 1
                task_ref = self.client.collection(self.tasks_col).document(rec.task_id)
                txn.set(task_ref, rec.to_dict())
                return rec
            return None

        return _claim_in_tx(transaction)

