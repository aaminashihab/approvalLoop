from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field, field_validator
import uuid

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class GatewayDecisionEnum(str, Enum):
    ALLOW = "allow"
    REQUIRE_HUMAN_APPROVAL = "require_human_approval"
    DENY = "deny"

class AgentActionProposal(BaseModel):
    """
    Structured action proposal emitted by an institutional agent in the Gemini Agent Fleet.
    The LLM proposes; the Gateway verifies identity, policy, and validation before execution.
    """
    proposal_id: str = Field(default_factory=lambda: f"prop_{uuid.uuid4().hex[:10]}")
    workflow_id: str = Field(default_factory=lambda: f"wf_{uuid.uuid4().hex[:10]}")
    session_id: Optional[str] = None
    agent_id: str
    agent_version: str = "1.0.0"
    action_name: str  # e.g., 'issue_refund', 'approve_expense', 'credit_account', 'grant_discount'
    target_resource_id: str  # e.g., 'REF-2001', 'EXP-101', 'CUST-800'
    amount: Optional[Decimal] = None
    currency: str = "USD"
    recipient: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    justification: str = ""
    raw_llm_reasoning: Optional[str] = None
    proposed_at: datetime = Field(default_factory=utc_now)

    @field_validator("amount", mode="before")
    def parse_decimal_amount(cls, v: Any) -> Optional[Decimal]:
        if v is None:
            return None
        if isinstance(v, (int, str, float)):
            return Decimal(str(v))
        if isinstance(v, Decimal):
            return v
        raise ValueError(f"Invalid monetary value: {v}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "workflow_id": self.workflow_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "agent_version": self.agent_version,
            "action_name": self.action_name,
            "target_resource_id": self.target_resource_id,
            "amount": str(self.amount) if self.amount is not None else None,
            "currency": self.currency,
            "recipient": self.recipient,
            "parameters": self.parameters,
            "justification": self.justification,
            "raw_llm_reasoning": self.raw_llm_reasoning,
            "proposed_at": self.proposed_at.isoformat(),
        }

class AgentAuthContext(BaseModel):
    """
    Authenticated cryptographic identity information sent alongside agent action proposals.
    """
    agent_id: str
    agent_version: str
    request_id: str = Field(default_factory=lambda: f"req_{uuid.uuid4().hex[:10]}")
    issued_at: str = Field(default_factory=lambda: utc_now().isoformat())
    token: Optional[str] = None
    signature: Optional[str] = None
    verified: bool = False
    verification_method: Optional[str] = None
    claims: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_version": self.agent_version,
            "request_id": self.request_id,
            "issued_at": self.issued_at,
            "verified": self.verified,
            "verification_method": self.verification_method,
            "claims": self.claims,
        }

class GatewayDecision(BaseModel):
    """
    Structured authorization decision returned by the ApprovalLoop Agent Gateway.
    """
    decision_id: str = Field(default_factory=lambda: f"dec_{uuid.uuid4().hex[:10]}")
    proposal_id: str
    workflow_id: str
    agent_id: str
    action_name: str
    decision: GatewayDecisionEnum
    reason: str
    policy_version: str
    risk_level: str
    identity_verified: bool = True
    validation_passed: bool = True
    safety_guardrail_passed: bool = True
    requires_human_approval: bool = False
    action_record_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=utc_now)
    details: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "proposal_id": self.proposal_id,
            "workflow_id": self.workflow_id,
            "agent_id": self.agent_id,
            "action_name": self.action_name,
            "decision": self.decision.value,
            "reason": self.reason,
            "policy_version": self.policy_version,
            "risk_level": self.risk_level,
            "identity_verified": self.identity_verified,
            "validation_passed": self.validation_passed,
            "safety_guardrail_passed": self.safety_guardrail_passed,
            "requires_human_approval": self.requires_human_approval,
            "action_record_id": self.action_record_id,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
        }
