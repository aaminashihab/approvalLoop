from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field, field_validator
import uuid

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class ReportStatus(str, Enum):
    PENDING = "Pending"
    NUDGED = "Nudged"
    ESCALATED = "Escalated"
    RESOLVED = "Resolved"

class ActionType(str, Enum):
    NUDGE = "nudge"
    ESCALATE = "escalate"

class ActionStatus(str, Enum):
    CLAIMED = "claimed"
    PROCESSING = "processing"
    SENT = "sent"
    COMPLETED = "completed"
    FAILED = "failed"       # Operational failure -> retryable with backoff
    BLOCKED = "blocked"     # Safety violation -> terminal, requires audit

class ValidatorResultEnum(str, Enum):
    PASS = "pass"
    BLOCKED = "blocked"

class StateTransitionResult(str, Enum):
    APPLIED = "applied"
    SKIPPED = "skipped"

class ExpenseReport(BaseModel):
    report_id: str
    status: ReportStatus = ReportStatus.PENDING
    submitter_name: str
    submitter_email: str
    approver_email: str
    backup_approver_email: Optional[str] = None
    amount: Decimal
    currency: str = "USD"
    description: str
    submitted_at: datetime = Field(default_factory=utc_now)
    last_nudged_at: Optional[datetime] = None
    escalated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    @field_validator("amount", mode="before")
    def parse_decimal_amount(cls, v: Any) -> Decimal:
        if isinstance(v, (int, str)):
            return Decimal(str(v))
        if isinstance(v, float):
            return Decimal(str(v))
        if isinstance(v, Decimal):
            return v
        raise ValueError(f"Invalid monetary value: {v}")

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "status": self.status.value,
            "submitter_name": self.submitter_name,
            "submitter_email": self.submitter_email,
            "approver_email": self.approver_email,
            "backup_approver_email": self.backup_approver_email,
            "amount": str(self.amount),
            "currency": self.currency,
            "description": self.description,
            "submitted_at": self.submitted_at.isoformat(),
            "last_nudged_at": self.last_nudged_at.isoformat() if self.last_nudged_at else None,
            "escalated_at": self.escalated_at.isoformat() if self.escalated_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }

class NotificationEnvelope(BaseModel):
    """Authoritative notification payload constructed deterministically by code."""
    report_id: str
    amount: Decimal
    currency: str
    recipient: str
    submitter_name: str
    subject: str
    body_text: str  # Gemini 3.7 drafts the wording
    raw_llm_draft: Optional[str] = None

    @field_validator("amount", mode="before")
    def parse_decimal_amount(cls, v: Any) -> Decimal:
        if isinstance(v, (int, str, float)):
            return Decimal(str(v))
        if isinstance(v, Decimal):
            return v
        raise ValueError(f"Invalid monetary value: {v}")

class ValidatorCheckDetails(BaseModel):
    """4-Point Deterministic Safety Validator Checklist."""
    recipient_verified: bool = True
    report_id_verified: bool = True
    amount_verified: bool = True
    state_verified: bool = True

class ActionRecord(BaseModel):
    """Full operational outbox ledger matching frozen spec Section 3 and production requirements."""
    action_id: str = Field(default_factory=lambda: f"act_{uuid.uuid4().hex[:12]}")
    report_id: str
    action_type: ActionType
    source_state: ReportStatus
    target_state: ReportStatus
    tick_id: str
    idempotency_key: str  # Transactional claim key: {report_id}:{action_type}
    recipient: str
    amount: Decimal
    
    # Lifecycle status
    status: ActionStatus = ActionStatus.CLAIMED
    created_at: datetime = Field(default_factory=utc_now)
    claimed_at: Optional[datetime] = None
    
    # Retry management
    attempt_count: int = 0
    max_attempts: int = 3
    last_error: Optional[str] = None
    next_attempt_at: Optional[datetime] = None

    # Gemini Output & Deterministic Envelope
    envelope: Optional[NotificationEnvelope] = None
    message: Optional[str] = None
    
    # 4-Point Deterministic Safety Validator Results
    validator_result: Optional[ValidatorResultEnum] = None
    validator_reason: Optional[str] = None
    validator_checks: ValidatorCheckDetails = Field(default_factory=ValidatorCheckDetails)
    
    # Delivery
    sent_at: Optional[datetime] = None
    notification_id: Optional[str] = None
    
    # Conditional State Transition (Scenario 13 Race Guard)
    state_transition: Optional[StateTransitionResult] = None
    skip_reason: Optional[str] = None
    completed_at: Optional[datetime] = None

    @field_validator("amount", mode="before")
    def parse_decimal_amount(cls, v: Any) -> Decimal:
        if isinstance(v, (int, str, float)):
            return Decimal(str(v))
        if isinstance(v, Decimal):
            return v
        raise ValueError(f"Invalid monetary value: {v}")

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "report_id": self.report_id,
            "action_type": self.action_type.value,
            "source_state": self.source_state.value,
            "target_state": self.target_state.value,
            "tick_id": self.tick_id,
            "idempotency_key": self.idempotency_key,
            "recipient": self.recipient,
            "amount": str(self.amount),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "claimed_at": self.claimed_at.isoformat() if self.claimed_at else None,
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "last_error": self.last_error,
            "next_attempt_at": self.next_attempt_at.isoformat() if self.next_attempt_at else None,
            "message": self.message,
            "validator_result": self.validator_result.value if self.validator_result else None,
            "validator_reason": self.validator_reason,
            "validator_checks": self.validator_checks.model_dump(),
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "notification_id": self.notification_id,
            "state_transition": self.state_transition.value if self.state_transition else None,
            "skip_reason": self.skip_reason,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "envelope": {
                "report_id": self.envelope.report_id,
                "amount": str(self.envelope.amount),
                "currency": self.envelope.currency,
                "recipient": self.envelope.recipient,
                "submitter_name": self.envelope.submitter_name,
                "subject": self.envelope.subject,
                "body_text": self.envelope.body_text,
            } if self.envelope else None
        }

class AutonomyMetrics(BaseModel):
    last_wake_up: Optional[str] = None
    reports_observed: int = 0
    eligible_reports: int = 0
    actions_claimed: int = 0
    notifications_sent: int = 0
    escalations_count: int = 0
    blocked_actions_count: int = 0
    duplicate_actions_prevented: int = 0
    unsafe_transitions_prevented: int = 0
    human_prompts_required: int = 0  # Hard zero
