from datetime import timedelta
from approval_loop.storage.base import BaseRepository
from approval_loop.domain.models import (
    ExpenseReport, ActionRecord, ReportStatus, ActionStatus,
    StateTransitionResult, utc_now
)
from google.cloud import firestore

class FirestoreRepository(BaseRepository):
    def __init__(self, project_id: str, reports_col: str = "expense_reports", actions_col: str = "approval_actions"):
        self.client = firestore.Client(project=project_id)
        self.reports_col = reports_col
        self.actions_col = actions_col

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
