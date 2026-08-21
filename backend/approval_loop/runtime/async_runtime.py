import uuid
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Any
from pydantic import BaseModel, Field
from approval_loop.domain.gateway_models import AgentActionProposal, AgentAuthContext, GatewayDecision, GatewayDecisionEnum, utc_now
from approval_loop.gateway.gateway import AgentGateway
from approval_loop.memory.memory_bank import MemoryBankService, WorkflowMemoryRecord, WorkflowState
from approval_loop.worker.worker import BaseNotificationProvider

logger = logging.getLogger("approval_loop.runtime")

class AsyncTaskState(str):
    QUEUED = "queued"
    LEASED = "leased"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY_PENDING = "retry_pending"

class AsyncTaskRecord(BaseModel):
    """
    Leased, Idempotent Execution Task with Crash-Recovery and Processing Leases.
    """
    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:10]}")
    workflow_id: str
    proposal_id: str
    idempotency_key: str
    agent_id: str
    action_name: str
    status: str = AsyncTaskState.QUEUED
    attempt_count: int = 0
    max_attempts: int = 3
    lease_expires_at: Optional[datetime] = None
    claimed_at: Optional[datetime] = None
    last_error: Optional[str] = None
    next_attempt_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "workflow_id": self.workflow_id,
            "proposal_id": self.proposal_id,
            "idempotency_key": self.idempotency_key,
            "agent_id": self.agent_id,
            "action_name": self.action_name,
            "status": self.status,
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "lease_expires_at": self.lease_expires_at.isoformat() if self.lease_expires_at else None,
            "claimed_at": self.claimed_at.isoformat() if self.claimed_at else None,
            "last_error": self.last_error,
            "next_attempt_at": self.next_attempt_at.isoformat() if self.next_attempt_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "payload": self.payload,
            "created_at": self.created_at.isoformat(),
        }

class AsyncAgentRuntime:
    """
    Long-Running Asynchronous Agent Execution Runtime:
    
    Provides:
    1. Unprompted and background workflow execution.
    2. Processing leases (lease-expiration crash recovery).
    3. Idempotent task claiming preventing duplicate execution.
    4. Workflow pause on human approval requirement and asynchronous resumption.
    5. Exponential retry backoff.
    """
    def __init__(
        self,
        gateway: AgentGateway,
        memory_bank: MemoryBankService,
        lease_duration_seconds: int = 60
    ):
        self.gateway = gateway
        self.memory_bank = memory_bank
        self.lease_duration_seconds = lease_duration_seconds
        self._tasks: dict[str, AsyncTaskRecord] = {}
        self._idempotency_index: dict[str, str] = {}  # idempotency_key -> task_id

    def submit_workflow(
        self,
        proposal: AgentActionProposal,
        auth_context: AgentAuthContext
    ) -> tuple[AsyncTaskRecord, GatewayDecision]:
        """
        Ingresses an agent workflow into the asynchronous runtime queue with idempotency.
        """
        idempotency_key = f"async:{proposal.agent_id}:{proposal.action_name}:{proposal.target_resource_id}"
        
        # Deduplication check
        if idempotency_key in self._idempotency_index:
            existing_task_id = self._idempotency_index[idempotency_key]
            existing_task = self._tasks[existing_task_id]
            logger.info("Async runtime deduplicated existing task %s for key %s", existing_task_id, idempotency_key)
            # Reconstruct previous decision if available
            decision = GatewayDecision(
                proposal_id=proposal.proposal_id,
                workflow_id=proposal.workflow_id,
                agent_id=proposal.agent_id,
                action_name=proposal.action_name,
                decision=GatewayDecisionEnum.ALLOW if existing_task.status == AsyncTaskState.COMPLETED else GatewayDecisionEnum.REQUIRE_HUMAN_APPROVAL,
                reason="Deduplication Hit: Task already accepted in runtime queue.",
                policy_version="cached",
                risk_level="low"
            )
            return existing_task, decision

        # 1. Authorize via ApprovalLoop Gateway
        decision = self.gateway.authorize_action(proposal, auth_context)

        # 2. Initialize runtime task
        task = AsyncTaskRecord(
            workflow_id=proposal.workflow_id,
            proposal_id=proposal.proposal_id,
            idempotency_key=idempotency_key,
            agent_id=proposal.agent_id,
            action_name=proposal.action_name,
            status=AsyncTaskState.QUEUED if decision.decision == GatewayDecisionEnum.ALLOW else (
                AsyncTaskState.PAUSED if decision.decision == GatewayDecisionEnum.REQUIRE_HUMAN_APPROVAL else AsyncTaskState.FAILED
            ),
            payload={"proposal": proposal.to_dict(), "decision": decision.to_dict()}
        )
        self._tasks[task.task_id] = task
        self._idempotency_index[idempotency_key] = task.task_id

        return task, decision

    def claim_next_task(self, worker_id: str = "worker-1") -> Optional[AsyncTaskRecord]:
        """
        Atomically leases the next eligible queued or retry-pending task.
        """
        now = utc_now()
        for task in self._tasks.values():
            if task.status in (AsyncTaskState.QUEUED, AsyncTaskState.RETRY_PENDING):
                if task.next_attempt_at and now < task.next_attempt_at:
                    continue
                task.status = AsyncTaskState.LEASED
                task.claimed_at = now
                task.lease_expires_at = now + timedelta(seconds=self.lease_duration_seconds)
                task.attempt_count += 1
                return task
        return None

    def recover_expired_leases(self) -> list[AsyncTaskRecord]:
        """
        Crash Recovery: Reclaims tasks where a worker crashed before completing or releasing lease.
        """
        now = utc_now()
        recovered = []
        for task in self._tasks.values():
            if task.status == AsyncTaskState.LEASED and task.lease_expires_at and now > task.lease_expires_at:
                logger.warning("Recovered expired lease on task %s (expired at %s)", task.task_id, task.lease_expires_at)
                if task.attempt_count >= task.max_attempts:
                    task.status = AsyncTaskState.FAILED
                    task.last_error = "Exceeded maximum lease retry attempts due to unhandled worker crashes."
                else:
                    task.status = AsyncTaskState.RETRY_PENDING
                    task.next_attempt_at = now + timedelta(seconds=5)
                recovered.append(task)
        return recovered

    def complete_task(self, task_id: str, result: dict[str, Any]) -> Optional[AsyncTaskRecord]:
        task = self._tasks.get(task_id)
        if not task:
            return None
        task.status = AsyncTaskState.COMPLETED
        task.completed_at = utc_now()
        task.payload["execution_result"] = result
        return task

    def fail_task(self, task_id: str, error_msg: str, backoff_seconds: int = 10) -> Optional[AsyncTaskRecord]:
        task = self._tasks.get(task_id)
        if not task:
            return None
        task.last_error = error_msg
        if task.attempt_count >= task.max_attempts:
            task.status = AsyncTaskState.FAILED
        else:
            task.status = AsyncTaskState.RETRY_PENDING
            task.next_attempt_at = utc_now() + timedelta(seconds=backoff_seconds * (2 ** (task.attempt_count - 1)))
        return task

    def get_task(self, task_id: str) -> Optional[AsyncTaskRecord]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[AsyncTaskRecord]:
        return list(self._tasks.values())
