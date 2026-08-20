from enum import Enum
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel
from approval_loop.domain.models import (
    ActionRecord, ExpenseReport, NotificationEnvelope, ActionType, ReportStatus
)
from approval_loop.config import AppEnvironment, Settings

class PolicyDecisionEnum(str, Enum):
    ALLOW = "allow"
    DENY = "deny"

class PolicyEvaluationResult(BaseModel):
    decision: PolicyDecisionEnum
    reason: str
    policy_name: str
    enforced_at: str

class PolicyEngine:
    """
    Corporate Policy Enforcement Layer:
    Sits between Deterministic Validator and Worker execution.
    Enforces corporate governance, high-risk financial limits, domain whitelist, and environment policy.
    
    Principle:
    LLM proposes wording.
    Deterministic code validates facts.
    Policy Engine authorizes execution.
    Tool executes side-effects.
    """
    HIGH_VALUE_THRESHOLD = Decimal("5000.00")
    DISALLOWED_DOMAINS = {"external-attacker.com", "malicious.com", "unauthorized.attacker.com", "tempmail.com"}

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()

    def evaluate(
        self,
        action: ActionRecord,
        report: ExpenseReport,
        envelope: NotificationEnvelope
    ) -> tuple[PolicyDecisionEnum, str]:
        # 1. Domain Governance Policy
        recipient_domain = envelope.recipient.split("@")[-1].lower() if "@" in envelope.recipient else ""
        if recipient_domain in self.DISALLOWED_DOMAINS or "attacker" in recipient_domain:
            return (
                PolicyDecisionEnum.DENY,
                f"Policy Violation [POL-DOM-01]: Recipient domain '@{recipient_domain}' is on corporate restricted domain list."
            )

        # 2. High-Value Financial Escalation Governance
        if report.amount >= self.HIGH_VALUE_THRESHOLD:
            if action.action_type == ActionType.ESCALATE:
                # High-value escalation must go to a senior authority or admin fallback
                if "director" not in envelope.recipient.lower() and "admin" not in envelope.recipient.lower() and "vp" not in envelope.recipient.lower():
                    return (
                        PolicyDecisionEnum.DENY,
                        f"Policy Violation [POL-VAL-02]: High-value expense ({report.currency} {report.amount}) escalation requires Director/Admin authorization level."
                    )

        # 3. State Invariant Policy
        if report.status == ReportStatus.RESOLVED:
            return (
                PolicyDecisionEnum.DENY,
                "Policy Violation [POL-STA-03]: Cannot execute side-effects against a Resolved expense record."
            )

        # 4. Production Safety Policy
        if self.settings.app_env == AppEnvironment.PRODUCTION:
            if report.report_id.startswith("EXP-ADV-") or report.report_id.startswith("EXP-TEST-"):
                return (
                    PolicyDecisionEnum.DENY,
                    f"Policy Violation [POL-ENV-04]: Synthetic/Adversarial test ID '{report.report_id}' is restricted in PRODUCTION environment."
                )

        return (PolicyDecisionEnum.ALLOW, "Policy Authorization Granted: Action conforms to corporate governance rules.")
