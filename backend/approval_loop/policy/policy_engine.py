from enum import Enum
from decimal import Decimal
from typing import Optional, Any
from pydantic import BaseModel
from approval_loop.domain.models import (
    ActionRecord, ExpenseReport, NotificationEnvelope, ActionType, ReportStatus
)
from approval_loop.domain.gateway_models import AgentActionProposal
from approval_loop.config import AppEnvironment, Settings

class PolicyDecisionEnum(str, Enum):
    ALLOW = "allow"
    REQUIRE_HUMAN_APPROVAL = "require_human_approval"
    DENY = "deny"

class PolicyEvaluationResult(BaseModel):
    decision: PolicyDecisionEnum
    reason: str
    policy_name: str
    enforced_at: str

class PolicyEngine:
    """
    Corporate Deterministic Policy Enforcement Layer:
    
    Principles:
    1. AI proposes. Deterministic policy decides. Infrastructure executes.
    2. Zero non-deterministic authority: The LLM may propose or recommend, but policy determines
       ALLOW vs REQUIRE_HUMAN_APPROVAL vs DENY.
    3. Reproducibility: Policy decisions are 100% reproducible from structured input and versioned profiles.
    
    Profiles supported:
    - 'finance-v3': Tiered financial governance (< 5,000 auto, 5,000-25,000 human approval, > 25,000 deny)
    - 'support-v1': Tiered customer credit governance (< 2,000 auto, 2,000-10,000 human approval, > 10,000 deny)
    - 'sales-v1': Deal discount governance (<= 10% auto, 11-30% human approval, > 30% deny)
    """
    HIGH_VALUE_THRESHOLD = Decimal("5000.00")
    DISALLOWED_DOMAINS = {"external-attacker.com", "malicious.com", "unauthorized.attacker.com", "tempmail.com"}

    # Policy profile threshold configurations (supports both USD and INR normalization)
    PROFILES = {
        "finance-v3": {
            "version": "finance-v3.2.0",
            "auto_approve_max": Decimal("5000.00"),     # < 5000 -> ALLOW (or < 50.00 for USD)
            "human_approval_max": Decimal("25000.00"), # 5000-25000 -> REQUIRE_HUMAN_APPROVAL
            "auto_approve_usd": Decimal("50.00"),
            "human_approval_usd": Decimal("250.00"),
        },
        "support-v1": {
            "version": "support-v1.1.0",
            "auto_approve_max": Decimal("2000.00"),     # < 2000 -> ALLOW
            "human_approval_max": Decimal("10000.00"), # 2000-10000 -> REQUIRE_HUMAN_APPROVAL
            "auto_approve_usd": Decimal("20.00"),
            "human_approval_usd": Decimal("100.00"),
        },
        "sales-v1": {
            "version": "sales-v1.0.0",
            "auto_discount_percent": Decimal("10.0"),  # <= 10% -> ALLOW
            "human_discount_percent": Decimal("30.0"), # 11-30% -> REQUIRE_HUMAN_APPROVAL
        }
    }

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()

    def evaluate(
        self,
        action: ActionRecord,
        report: ExpenseReport,
        envelope: NotificationEnvelope
    ) -> tuple[PolicyDecisionEnum, str]:
        """
        Evaluates legacy/expense approval actions against corporate governance policy.
        Maintains backward compatibility with core ApprovalEngine tick pipeline.
        """
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

    def evaluate_proposal(
        self,
        proposal: AgentActionProposal,
        profile_name: str = "finance-v3"
    ) -> tuple[PolicyDecisionEnum, str, str]:
        """
        Evaluates a structured proposal from the Gemini Agent Fleet against versioned deterministic policies.
        Returns: (decision: PolicyDecisionEnum, reason: str, policy_version: str)
        """
        profile = self.PROFILES.get(profile_name, self.PROFILES["finance-v3"])
        policy_version = profile["version"]

        # 1. Global Domain Security Policy
        recipient_domain = proposal.recipient.split("@")[-1].lower() if "@" in proposal.recipient else ""
        if recipient_domain in self.DISALLOWED_DOMAINS or "attacker" in recipient_domain:
            return (
                PolicyDecisionEnum.DENY,
                f"Policy Violation [POL-DOM-01]: Recipient domain '@{recipient_domain}' is on corporate restricted domain list.",
                policy_version
            )

        # 2. Production Environment Guard
        if self.settings.app_env == AppEnvironment.PRODUCTION:
            if proposal.target_resource_id.startswith("TEST-") or proposal.target_resource_id.startswith("ADV-"):
                return (
                    PolicyDecisionEnum.DENY,
                    f"Policy Violation [POL-ENV-04]: Test/Adversarial ID '{proposal.target_resource_id}' restricted in PRODUCTION.",
                    policy_version
                )

        # 3. Profile-Specific Governance
        if profile_name.startswith("finance"):
            amount = proposal.amount or Decimal("0.00")
            currency = proposal.currency.upper()

            # Handle both INR and USD limits
            auto_limit = profile["auto_approve_max"] if currency == "INR" else profile.get("auto_approve_usd", Decimal("50.00"))
            human_limit = profile["human_approval_max"] if currency == "INR" else profile.get("human_approval_usd", Decimal("250.00"))

            # Special case for INR 5000 / 25000 thresholds
            if amount < auto_limit:
                return (
                    PolicyDecisionEnum.ALLOW,
                    f"Policy {policy_version}: Amount {currency} {amount} is within autonomous threshold (< {currency} {auto_limit}). Automatic execution permitted.",
                    policy_version
                )
            elif amount <= human_limit:
                return (
                    PolicyDecisionEnum.REQUIRE_HUMAN_APPROVAL,
                    f"Policy {policy_version}: Amount {currency} {amount} requires mandatory human sign-off ({currency} {auto_limit} - {currency} {human_limit}).",
                    policy_version
                )
            else:
                return (
                    PolicyDecisionEnum.DENY,
                    f"Policy Violation [{policy_version}-LMT]: Amount {currency} {amount} exceeds corporate authorization ceiling (> {currency} {human_limit}). Consequential action DENIED.",
                    policy_version
                )

        elif profile_name.startswith("support"):
            amount = proposal.amount or Decimal("0.00")
            currency = proposal.currency.upper()
            auto_limit = profile["auto_approve_max"] if currency == "INR" else profile.get("auto_approve_usd", Decimal("20.00"))
            human_limit = profile["human_approval_max"] if currency == "INR" else profile.get("human_approval_usd", Decimal("100.00"))

            if amount < auto_limit:
                return (
                    PolicyDecisionEnum.ALLOW,
                    f"Policy {policy_version}: Support credit {currency} {amount} is within Tier-2 auto-allow limit.",
                    policy_version
                )
            elif amount <= human_limit:
                return (
                    PolicyDecisionEnum.REQUIRE_HUMAN_APPROVAL,
                    f"Policy {policy_version}: Support credit {currency} {amount} exceeds autonomous limit and requires Supervisor approval.",
                    policy_version
                )
            else:
                return (
                    PolicyDecisionEnum.DENY,
                    f"Policy Violation [{policy_version}-LMT]: Support credit {currency} {amount} exceeds max credit limit ({currency} {human_limit}). Action DENIED.",
                    policy_version
                )

        elif profile_name.startswith("sales"):
            discount_pct = Decimal(str(proposal.parameters.get("discount_percent", 0)))
            auto_pct = profile["auto_discount_percent"]
            human_pct = profile["human_discount_percent"]

            if discount_pct <= auto_pct:
                return (
                    PolicyDecisionEnum.ALLOW,
                    f"Policy {policy_version}: Discount {discount_pct}% is within standard account executive limit (<= {auto_pct}%).",
                    policy_version
                )
            elif discount_pct <= human_pct:
                return (
                    PolicyDecisionEnum.REQUIRE_HUMAN_APPROVAL,
                    f"Policy {policy_version}: Discount {discount_pct}% exceeds AE authority (10%-30%) and requires VP Sales approval.",
                    policy_version
                )
            else:
                return (
                    PolicyDecisionEnum.DENY,
                    f"Policy Violation [{policy_version}-DSC]: Discount {discount_pct}% exceeds max discount ceiling ({human_pct}%). Action DENIED.",
                    policy_version
                )

        return (PolicyDecisionEnum.ALLOW, f"Policy {policy_version}: Action passed default governance rules.", policy_version)
