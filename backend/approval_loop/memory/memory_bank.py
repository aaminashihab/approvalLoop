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
    FAILED = "failed"

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
        self._lock = threading.Lock()

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowMemoryRecord]:
        if self.repo and hasattr(self.repo, "get_workflow_memory"):
            return self.repo.get_workflow_memory(workflow_id)
        with self._lock:
            return self._in_memory_records.get(workflow_id)

    def get_workflow_by_action_id(self, action_id: str) -> Optional[WorkflowMemoryRecord]:
        """Finds a workflow memory record by its action ID across durable storage."""
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

    def claim_and_transition_approval(
        self,
        action_id: str,
        approve: bool,
        operator: str,
        notes: str = ""
    ) -> tuple[bool, str, Optional[WorkflowMemoryRecord]]:
        """
        Atomically claims a pending approval action and transitions its state.
        Guarantees that concurrent approval requests result in exactly ONE successful transition.
        """
        with self._lock:
            rec = self.get_workflow_by_action_id(action_id)
            if not rec:
                return False, f"Pending action '{action_id}' not found in durable approval queue.", None

            if rec.state == WorkflowState.APPROVED:
                return False, f"Action '{action_id}' has already been approved.", rec
            elif rec.state == WorkflowState.REJECTED:
                return False, f"Action '{action_id}' has already been rejected.", rec
            elif rec.state == WorkflowState.COMPLETED:
                return False, f"Action '{action_id}' has already been completed.", rec
            elif rec.state != WorkflowState.PAUSED_FOR_APPROVAL:
                return False, f"Action '{action_id}' is in state '{rec.state.value}' and not pending approval.", rec

            now = utc_now()
            rec.resumed_at = now
            rec.approval_record.status = "approved" if approve else "rejected"
            rec.approval_record.decided_at = now
            rec.approval_record.decided_by = operator
            rec.approval_record.operator_notes = notes

            if approve:
                rec.state = WorkflowState.APPROVED
            else:
                rec.state = WorkflowState.REJECTED
                rec.completed_at = now

            self.save_workflow(rec)
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

    def complete_workflow(self, workflow_id: str, final_tool_result: dict[str, Any]) -> WorkflowMemoryRecord:
        rec = self.get_workflow(workflow_id)
        if not rec:
            raise ValueError(f"Workflow '{workflow_id}' not found.")
        rec.state = WorkflowState.COMPLETED
        rec.completed_at = utc_now()
        rec.tool_results.append(final_tool_result)
        return self.save_workflow(rec)
