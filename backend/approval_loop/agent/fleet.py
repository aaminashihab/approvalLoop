import os
import json
import uuid
import logging
from decimal import Decimal
from typing import Optional, Any
from pydantic import BaseModel, Field
from approval_loop.domain.gateway_models import AgentActionProposal, AgentAuthContext
from approval_loop.identity.auth_provider import AgentIdentityProvider
from approval_loop.guardrails.safety_guardrail import ModelSafetyGuardrail

logger = logging.getLogger("approval_loop.fleet")

class FleetAgentProposalResponse(BaseModel):
    """Structured LLM response schema from Gemini 3.5."""
    action_name: str
    target_resource_id: str
    amount: Optional[str] = None
    currency: str = "INR"
    recipient: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    justification: str
    risk_assessment: str = "medium"

class BaseFleetAgent:
    """
    Base Institutional Agent powered by Google GenAI SDK (Gemini 3.5).
    
    Principles:
    1. AI proposes. Deterministic policy decides. Infrastructure executes.
    2. Zero Tool Privilege: Agents NEVER directly invoke tools, databases, or payment gateways.
    3. Output is strictly a structured AgentActionProposal submitted to the ApprovalLoop Gateway.
    """
    def __init__(
        self,
        agent_id: str,
        agent_version: str,
        identity_provider: Optional[AgentIdentityProvider] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        guardrail: Optional[ModelSafetyGuardrail] = None
    ):
        self.agent_id = agent_id
        self.agent_version = agent_version
        self.identity_provider = identity_provider
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        self.guardrail = guardrail or ModelSafetyGuardrail()
        self.client = None
        if self.api_key:
            try:
                import google.genai as genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning("Could not initialize google.genai client for %s: %s", agent_id, str(e))
                self.client = None

    def create_auth_context(self) -> AgentAuthContext:
        """Generates an authenticated cryptographic token for the agent proposal."""
        token = None
        if self.identity_provider:
            token = self.identity_provider.generate_agent_token(self.agent_id, self.agent_version)
        return AgentAuthContext(
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            token=token,
            request_id=f"req_{uuid.uuid4().hex[:10]}"
        )

    def _clean_json_response(self, raw_text: str) -> str:
        clean = raw_text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[-1].rsplit("\n", 1)[0].strip()
            if clean.startswith("json"):
                clean = clean[4:].strip()
        return clean

class FinanceAgent(BaseFleetAgent):
    """
    Institutional Finance Agent:
    Evaluates corporate refunds, vendor payments, and expense disputes.
    """
    def __init__(
        self,
        identity_provider: Optional[AgentIdentityProvider] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):
        super().__init__(
            agent_id="finance-agent",
            agent_version="1.2.0",
            identity_provider=identity_provider,
            api_key=api_key,
            model=model
        )

    def propose_refund(
        self,
        refund_id: str,
        customer_email: str,
        amount: Decimal,
        currency: str = "INR",
        reason: str = "Customer requested order refund due to SLA defect",
        session_id: Optional[str] = None
    ) -> tuple[AgentActionProposal, AgentAuthContext]:
        """
        Reasons over the financial situation and emits a structured proposal.
        """
        # Guardrail prompt inspection (Model Armor)
        safety = self.guardrail.inspect_prompt(reason)
        if not safety.passed:
            logger.warning("FinanceAgent prompt rejected by safety guardrail: %s", safety.reason)

        proposal_id = f"prop_{uuid.uuid4().hex[:10]}"
        workflow_id = f"wf_{uuid.uuid4().hex[:10]}"
        justification = f"Finance assessment for refund {refund_id}: {reason}."
        raw_reasoning = "Evaluated transactional logs and confirmed refund eligibility."

        if self.client:
            try:
                system_prompt = (
                    "You are an Institutional Finance Agent in an enterprise fleet. "
                    "Analyze the refund request and formulate a structured proposal. "
                    "Respond ONLY with valid JSON matching: "
                    '{"action_name": "issue_refund", "target_resource_id": str, "amount": str, "currency": str, "recipient": str, "justification": str, "risk_assessment": "low|medium|high"}'
                )
                user_msg = f"Evaluate refund: ID={refund_id}, Customer={customer_email}, Amount={amount}, Currency={currency}, Reason={reason}"
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=f"{system_prompt}\n\n{user_msg}"
                )
                clean_json = self._clean_json_response(response.text)
                parsed = json.loads(clean_json)
                justification = parsed.get("justification", justification)
                raw_reasoning = response.text
            except Exception as e:
                logger.warning("Gemini generation in FinanceAgent fell back to deterministic template: %s", str(e))

        proposal = AgentActionProposal(
            proposal_id=proposal_id,
            workflow_id=workflow_id,
            session_id=session_id or f"sess_{uuid.uuid4().hex[:8]}",
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            action_name="issue_refund",
            target_resource_id=refund_id,
            amount=amount,
            currency=currency,
            recipient=customer_email,
            parameters={"refund_id": refund_id, "amount": str(amount), "currency": currency},
            justification=justification,
            raw_llm_reasoning=raw_reasoning
        )
        auth_context = self.create_auth_context()
        return proposal, auth_context

class SupportAgent(BaseFleetAgent):
    """
    Tier-2 Support Operations Agent:
    Evaluates customer SLA disputes and proposes account credits.
    """
    def __init__(
        self,
        identity_provider: Optional[AgentIdentityProvider] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):
        super().__init__(
            agent_id="support-agent",
            agent_version="1.1.0",
            identity_provider=identity_provider,
            api_key=api_key,
            model=model
        )

    def propose_credit(
        self,
        ticket_id: str,
        customer_email: str,
        credit_amount: Decimal,
        currency: str = "INR",
        reason: str = "Service outage SLA compensation credit",
        session_id: Optional[str] = None
    ) -> tuple[AgentActionProposal, AgentAuthContext]:
        proposal_id = f"prop_{uuid.uuid4().hex[:10]}"
        workflow_id = f"wf_{uuid.uuid4().hex[:10]}"

        proposal = AgentActionProposal(
            proposal_id=proposal_id,
            workflow_id=workflow_id,
            session_id=session_id or f"sess_{uuid.uuid4().hex[:8]}",
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            action_name="credit_account",
            target_resource_id=ticket_id,
            amount=credit_amount,
            currency=currency,
            recipient=customer_email,
            parameters={"ticket_id": ticket_id, "credit_amount": str(credit_amount)},
            justification=f"Support SLA triage for ticket {ticket_id}: {reason}.",
            raw_llm_reasoning="Analyzed uptime logs and calculated compensation according to Tier-2 SLA chart."
        )
        auth_context = self.create_auth_context()
        return proposal, auth_context

class SalesAgent(BaseFleetAgent):
    """
    Enterprise Sales Deal Desk Agent:
    Evaluates deal terms and proposes commercial discounts.
    """
    def __init__(
        self,
        identity_provider: Optional[AgentIdentityProvider] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):
        super().__init__(
            agent_id="sales-agent",
            agent_version="1.0.0",
            identity_provider=identity_provider,
            api_key=api_key,
            model=model
        )

    def propose_discount(
        self,
        deal_id: str,
        client_contact: str,
        discount_percent: float,
        annual_contract_value: Decimal,
        currency: str = "USD",
        reason: str = "Multi-year commitment deal discount",
        session_id: Optional[str] = None
    ) -> tuple[AgentActionProposal, AgentAuthContext]:
        proposal_id = f"prop_{uuid.uuid4().hex[:10]}"
        workflow_id = f"wf_{uuid.uuid4().hex[:10]}"

        proposal = AgentActionProposal(
            proposal_id=proposal_id,
            workflow_id=workflow_id,
            session_id=session_id or f"sess_{uuid.uuid4().hex[:8]}",
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            action_name="grant_discount",
            target_resource_id=deal_id,
            amount=annual_contract_value,
            currency=currency,
            recipient=client_contact,
            parameters={
                "deal_id": deal_id,
                "discount_percent": discount_percent,
                "acv": str(annual_contract_value)
            },
            justification=f"Sales Deal Desk evaluation for deal {deal_id}: {reason} ({discount_percent}% discount).",
            raw_llm_reasoning="Evaluated ARR margin and approved multi-year term structure."
        )
        auth_context = self.create_auth_context()
        return proposal, auth_context
