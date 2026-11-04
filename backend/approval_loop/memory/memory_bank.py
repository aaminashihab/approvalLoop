import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field
import uuid
import logging

logger = logging.getLogger("approval_loop.memory")

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class WorkflowState(str, Enum):
    INITIALIZED = "initialized"
    RUNNING = "running"
    PAUSED_FOR_APPROVAL = "paused_for_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"      # execution was attempted and failed
    DENIED = "denied"      # blocked by identity, safety or policy; nothing was executed

class ApprovalRecord(BaseModel):
    required: bool = False
    status: str = "none"  # "none" | "pending" | "approved" | "rejected"
    action_id: Optional[str] = None
    proposal_id: Optional[str] = None
    policy_version: Optional[str] = None
    requested_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None
    operator_notes: Optional[str] = None
    correlation_id: Optional[str] = None

class WorkflowMemoryRecord(BaseModel):
    """
    Persistent Memory Bank Record:
    Enables long-running asynchronous workflows across sessions with structured state,
    action history, gateway decisions, tool results, and pause/resume capability.
    """
    workflow_id: str = Field(default_factory=lambda: f"wf_{uuid.uuid4().hex[:10]}")
    agent_id: str
    session_id: str = Field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:8]}")
    state: WorkflowState = WorkflowState.INITIALIZED
    current_action_id: Optional[str] = None
    policy_version: Optional[str] = None
    
    # Structured context & execution history
    action_history: list[dict[str, Any]] = Field(default_factory=list)
    previous_decisions: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    approval_record: ApprovalRecord = Field(default_factory=ApprovalRecord)
    
    # Timestamps
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    paused_at: Optional[datetime] = None
    resumed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "state": self.state.value,
            "current_action_id": self.current_action_id,
            "policy_version": self.policy_version,
            "action_history": self.action_history,
            "previous_decisions": self.previous_decisions,
            "tool_results": self.tool_results,
            "approval_record": self.approval_record.model_dump(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
            "resumed_at": self.resumed_at.isoformat() if self.resumed_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
        }

class MemoryBankService:
    """
    Storage-agnostic Memory Bank service managing persistent state across async workflow sessions.
    """
    def __init__(self, repo: Any = None):
        self.repo = repo
        self._in_memory_records: dict[str, WorkflowMemoryRecord] = {}
        self._lock = threading.RLock()

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowMemoryRecord]:
        if self.repo and hasattr(self.repo, "get_workflow_memory"):
            return self.repo.get_workflow_memory(workflow_id)
        with self._lock:
            return self._in_memory_records.get(workflow_id)

    def get_workflow_by_action_id(self, action_id: str) -> Optional[WorkflowMemoryRecord]:
        """Finds a workflow memory record by its action ID (indexed lookup when a repository is set)."""
        if self.repo is not None:
            return self.repo.find_workflow_memory_by_action_id(action_id)
        records = self.list_workflows()
        for rec in records:
            if rec.current_action_id == action_id:
                return rec
            if rec.approval_record and rec.approval_record.action_id == action_id:
                return rec
            if rec.metadata and rec.metadata.get("pending_action", {}).get("action_id") == action_id:
                return rec
        return None

    def save_workflow(self, record: WorkflowMemoryRecord) -> WorkflowMemoryRecord:
        record.updated_at = utc_now()
        if self.repo and hasattr(self.repo, "save_workflow_memory"):
            self.repo.save_workflow_memory(record)
        else:
            with self._lock:
                self._in_memory_records[record.workflow_id] = record
        return record

    def list_workflows(self, agent_id: Optional[str] = None, state: Optional[WorkflowState] = None) -> list[WorkflowMemoryRecord]:
        if self.repo and hasattr(self.repo, "list_workflow_memories"):
            records = self.repo.list_workflow_memories(agent_id=agent_id, state=state.value if state else None)
        else:
            with self._lock:
                records = list(self._in_memory_records.values())

        if agent_id:
            records = [r for r in records if r.agent_id == agent_id]
        if state:
            records = [r for r in records if (r.state == state or r.state.value == (state.value if hasattr(state, "value") else str(state)))]
        return records

    def pause_for_approval(
        self,
        workflow_id: str,
        action_id: str,
        reason: str,
        policy_version: str,
        proposal_id: Optional[str] = None
    ) -> WorkflowMemoryRecord:
        """Pauses a workflow waiting for human sign-off."""
        rec = self.get_workflow(workflow_id)
        if not rec:
            raise ValueError(f"Workflow '{workflow_id}' not found in Memory Bank.")

        now = utc_now()
        rec.state = WorkflowState.PAUSED_FOR_APPROVAL
        rec.current_action_id = action_id
        rec.policy_version = policy_version
        rec.paused_at = now
        rec.approval_record = ApprovalRecord(
            required=True,
            status="pending",
            action_id=action_id,
            proposal_id=proposal_id,
            policy_version=policy_version,
            requested_at=now,
            operator_notes=reason
        )
        return self.save_workflow(rec)

    def record_decision(self, workflow_id: str, decision_dict: dict[str, Any]) -> WorkflowMemoryRecord:
        rec = self.get_workflow(workflow_id)
        if not rec:
            raise ValueError(f"Workflow '{workflow_id}' not found in Memory Bank.")
        rec.previous_decisions.append(decision_dict)
        return self.save_workflow(rec)

    def _commit_if_still_paused(self, rec: WorkflowMemoryRecord) -> bool:
        """Writes `rec` only if the stored copy is still paused. Atomic in the repository (lock or transaction)."""
        rec.updated_at = utc_now()
        if self.repo is not None:
            return self.repo.compare_and_set_workflow_memory(rec, WorkflowState.PAUSED_FOR_APPROVAL.value)
        current = self._in_memory_records.get(rec.workflow_id)
        if current is None or current.state != WorkflowState.PAUSED_FOR_APPROVAL:
            return False
        self._in_memory_records[rec.workflow_id] = rec
        return True

    @staticmethod
    def _already_decided(action_id: str, rec: Optional[WorkflowMemoryRecord]) -> str:
        if rec is None:
            return f"Pending action '{action_id}' not found in durable approval queue."
        if rec.state == WorkflowState.APPROVED:
            return f"Action '{action_id}' has already been approved."
        if rec.state == WorkflowState.REJECTED:
            return f"Action '{action_id}' has already been rejected."
        if rec.state == WorkflowState.COMPLETED:
            return f"Action '{action_id}' has already been completed."
        return f"Action '{action_id}' is in state '{rec.state.value}' and not pending approval."

    def claim_and_transition_approval(
        self,
        action_id: str,
        approve: bool,
        operator: str,
        notes: str = "",
        ttl_seconds: Optional[int] = None,
    ) -> tuple[bool, str, Optional[WorkflowMemoryRecord]]:
        """
        Claims a pending approval action and transitions its state. Exactly one concurrent caller wins.

        The decision is prepared on a private copy and committed with a compare-and-set that only
        succeeds if the stored workflow is still paused (repository lock in memory, a conditional UPDATE in
        PostgreSQL), so the guarantee holds across processes, not only within one.

        If `ttl_seconds` is given, an approval attempted after the request has aged beyond the TTL
        is refused and the workflow is moved to REJECTED (expired approvals can never execute).
        """
        with self._lock:
            stored = self.get_workflow_by_action_id(action_id)
            if not stored or stored.state != WorkflowState.PAUSED_FOR_APPROVAL:
                return False, self._already_decided(action_id, stored), stored

            rec = stored.model_copy(deep=True)
            now = utc_now()

            requested_at = rec.approval_record.requested_at if rec.approval_record else None
            if approve and ttl_seconds is not None and requested_at is not None:
                if (now - requested_at).total_seconds() > ttl_seconds:
                    rec.state = WorkflowState.REJECTED
                    rec.completed_at = now
                    rec.resumed_at = now
                    rec.approval_record.status = "expired"
                    rec.approval_record.decided_at = now
                    rec.approval_record.decided_by = "system:approval-expiry"
                    rec.approval_record.operator_notes = f"Approval window of {ttl_seconds}s elapsed before decision by {operator}."
                    self._commit_if_still_paused(rec)
                    return False, f"Action '{action_id}' approval has expired.", rec

            rec.resumed_at = now
            rec.approval_record.status = "approved" if approve else "rejected"
            rec.approval_record.decided_at = now
            rec.approval_record.decided_by = operator
            rec.approval_record.operator_notes = notes
            rec.state = WorkflowState.APPROVED if approve else WorkflowState.REJECTED
            if not approve:
                rec.completed_at = now

            if not self._commit_if_still_paused(rec):
                # Another process decided first; report what actually happened.
                latest = self.get_workflow_by_action_id(action_id)
                return False, self._already_decided(action_id, latest), latest
            return True, "Transition committed", rec

    def resume_workflow(
        self,
        workflow_id: str,
        approved: bool,
        operator: str,
        notes: str = ""
    ) -> WorkflowMemoryRecord:
        """Resumes a paused workflow following a human decision."""
        rec = self.get_workflow(workflow_id)
        if not rec:
            raise ValueError(f"Workflow '{workflow_id}' not found in Memory Bank.")

        now = utc_now()
        rec.resumed_at = now
        rec.approval_record.status = "approved" if approved else "rejected"
        rec.approval_record.decided_at = now
        rec.approval_record.decided_by = operator
        rec.approval_record.operator_notes = notes

        if approved:
            rec.state = WorkflowState.APPROVED
        else:
            rec.state = WorkflowState.REJECTED
            rec.completed_at = now

        return self.save_workflow(rec)

    def fail_workflow(self, workflow_id: str, error_result: dict[str, Any]) -> WorkflowMemoryRecord:
        """Marks a workflow FAILED after an execution failure and records the failure result."""
        rec = self.get_workflow(workflow_id)
        if not rec:
            raise ValueError(f"Workflow '{workflow_id}' not found.")
        rec.state = WorkflowState.FAILED
        rec.completed_at = utc_now()
        rec.tool_results.append(error_result)
        return self.save_workflow(rec)

    def complete_workflow(self, workflow_id: str, final_tool_result: dict[str, Any]) -> WorkflowMemoryRecord:
        rec = self.get_workflow(workflow_id)
        if not rec:
            raise ValueError(f"Workflow '{workflow_id}' not found.")
        rec.state = WorkflowState.COMPLETED
        rec.completed_at = utc_now()
        rec.tool_results.append(final_tool_result)
        return self.save_workflow(rec)
