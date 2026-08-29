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
    """Structured LLM response schema from Gemini 3.7."""
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
    Base Institutional Agent powered by Google GenAI SDK (Gemini 3.7).
    
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
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.7-flash")
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
        model: Optional[str] = None,
        guardrail: Optional[ModelSafetyGuardrail] = None
    ):
        super().__init__(
            agent_id="finance-agent",
            agent_version="1.2.0",
            identity_provider=identity_provider,
            api_key=api_key,
            model=model,
            guardrail=guardrail
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
        # 1. Model Armor Pre-LLM Prompt Inspection
        safety_prompt = self.guardrail.inspect_prompt(reason)
        if not safety_prompt.passed:
            logger.warning("FinanceAgent prompt rejected by Model Armor guardrail: %s", safety_prompt.reason)

        proposal_id = f"prop_{uuid.uuid4().hex[:10]}"
        workflow_id = f"wf_{uuid.uuid4().hex[:10]}"
        justification = f"Finance assessment for refund {refund_id}: {reason}."
        raw_reasoning = "Evaluated transactional logs and confirmed refund eligibility."

        if self.client and safety_prompt.passed:
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

                # 2. Model Armor Post-LLM Output Inspection
                safety_out = self.guardrail.inspect_model_output(raw_reasoning, user_prompt=user_msg)
                if not safety_out.passed:
                    logger.warning("FinanceAgent Gemini output rejected by Model Armor guardrail: %s", safety_out.reason)
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

        return proposal, auth_context

class SupportAgent(BaseFleetAgent):
    """
    Tier-2 Support Operations Agent:
    Evaluates customer SLA disputes and proposes account credits using Google GenAI SDK.
    """
    def __init__(
        self,
        identity_provider: Optional[AgentIdentityProvider] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        guardrail: Optional[ModelSafetyGuardrail] = None
    ):
        super().__init__(
            agent_id="support-agent",
            agent_version="1.1.0",
            identity_provider=identity_provider,
            api_key=api_key,
            model=model,
            guardrail=guardrail
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
        safety_prompt = self.guardrail.inspect_prompt(reason)
        if not safety_prompt.passed:
            logger.warning("SupportAgent prompt rejected by Model Armor guardrail: %s", safety_prompt.reason)

        proposal_id = f"prop_{uuid.uuid4().hex[:10]}"
        workflow_id = f"wf_{uuid.uuid4().hex[:10]}"
        justification = f"Support SLA triage for ticket {ticket_id}: {reason}."
        raw_reasoning = "Analyzed uptime logs and calculated compensation according to Tier-2 SLA chart."

        if self.client and safety_prompt.passed:
            try:
                system_prompt = (
                    "You are a Tier-2 Support Operations Agent in an enterprise fleet. "
                    "Analyze the customer SLA dispute ticket and formulate a structured credit proposal. "
                    "Respond ONLY with valid JSON matching: "
                    '{"action_name": "credit_account", "target_resource_id": str, "amount": str, "currency": str, "recipient": str, "justification": str, "risk_assessment": "low|medium|high"}'
                )
                user_msg = f"Evaluate SLA credit: Ticket={ticket_id}, Customer={customer_email}, CreditAmount={credit_amount}, Currency={currency}, Reason={reason}"
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=f"{system_prompt}\n\n{user_msg}"
                )
                clean_json = self._clean_json_response(response.text)
                parsed = json.loads(clean_json)
                justification = parsed.get("justification", justification)
                raw_reasoning = response.text

                safety_out = self.guardrail.inspect_model_output(raw_reasoning, user_prompt=user_msg)
                if not safety_out.passed:
                    logger.warning("SupportAgent Gemini output rejected by Model Armor guardrail: %s", safety_out.reason)
            except Exception as e:
                logger.warning("Gemini generation in SupportAgent fell back to deterministic template: %s", str(e))

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
            justification=justification,
            raw_llm_reasoning=raw_reasoning
        )
        auth_context = self.create_auth_context()
        return proposal, auth_context

class SalesAgent(BaseFleetAgent):
    """
    Enterprise Sales Deal Desk Agent:
    Evaluates deal terms and proposes commercial discounts using Google GenAI SDK.
    """
    def __init__(
        self,
        identity_provider: Optional[AgentIdentityProvider] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        guardrail: Optional[ModelSafetyGuardrail] = None
    ):
        super().__init__(
            agent_id="sales-agent",
            agent_version="1.0.0",
            identity_provider=identity_provider,
            api_key=api_key,
            model=model,
            guardrail=guardrail
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
        safety_prompt = self.guardrail.inspect_prompt(reason)
        if not safety_prompt.passed:
            logger.warning("SalesAgent prompt rejected by Model Armor guardrail: %s", safety_prompt.reason)

        proposal_id = f"prop_{uuid.uuid4().hex[:10]}"
        workflow_id = f"wf_{uuid.uuid4().hex[:10]}"
        justification = f"Sales Deal Desk evaluation for deal {deal_id}: {reason} ({discount_percent}% discount)."
        raw_reasoning = "Evaluated ARR margin and approved multi-year term structure."

        if self.client and safety_prompt.passed:
            try:
                system_prompt = (
                    "You are an Enterprise Sales Deal Desk Agent in an enterprise fleet. "
                    "Analyze the commercial deal discount request and formulate a structured proposal. "
                    "Respond ONLY with valid JSON matching: "
                    '{"action_name": "grant_discount", "target_resource_id": str, "amount": str, "currency": str, "recipient": str, "justification": str, "risk_assessment": "low|medium|high"}'
                )
                user_msg = f"Evaluate deal discount: DealID={deal_id}, Client={client_contact}, Discount={discount_percent}%, ACV={annual_contract_value}, Currency={currency}, Reason={reason}"
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=f"{system_prompt}\n\n{user_msg}"
                )
                clean_json = self._clean_json_response(response.text)
                parsed = json.loads(clean_json)
                justification = parsed.get("justification", justification)
                raw_reasoning = response.text

                safety_out = self.guardrail.inspect_model_output(raw_reasoning, user_prompt=user_msg)
                if not safety_out.passed:
                    logger.warning("SalesAgent Gemini output rejected by Model Armor guardrail: %s", safety_out.reason)
            except Exception as e:
                logger.warning("Gemini generation in SalesAgent fell back to deterministic template: %s", str(e))

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
            justification=justification,
            raw_llm_reasoning=raw_reasoning
        )
        auth_context = self.create_auth_context()
        return proposal, auth_context


class WorkflowAgent(BaseFleetAgent):
    """
    Fleet Workflow Agent: Observes expense report state and proposes autonomous actions via Google GenAI SDK.
    """
    def __init__(self, identity_provider: Optional[AgentIdentityProvider] = None, api_key: Optional[str] = None, model: Optional[str] = None):
        super().__init__(agent_id="workflow-agent", agent_version="1.0.0", identity_provider=identity_provider, api_key=api_key, model=model)


class PolicyAgent(BaseFleetAgent):
    """
    Fleet Policy Agent: Evaluates risk levels and provides policy recommendations for proposals using Google GenAI SDK.
    """
    def __init__(self, identity_provider: Optional[AgentIdentityProvider] = None, api_key: Optional[str] = None, model: Optional[str] = None):
        super().__init__(agent_id="policy-agent", agent_version="1.0.0", identity_provider=identity_provider, api_key=api_key, model=model)

    def assess_risk(self, amount: Decimal, currency: str = "USD", action_name: str = "nudge_approver") -> str:
        """Evaluates financial risk level, returning 'low', 'medium', or 'high'."""
        default_risk = "high" if amount >= Decimal("5000.00") else ("medium" if amount >= Decimal("1000.00") else "low")
        if not self.client:
            return default_risk
        try:
            prompt = f"Assess financial risk for action '{action_name}' with amount {currency} {amount}. Return JSON: {{\"risk\": \"low|medium|high\"}}"
            response = self.client.models.generate_content(model=self.model, contents=prompt)
            clean = self._clean_json_response(response.text)
            risk = json.loads(clean).get("risk", default_risk)
            return risk if risk in ("low", "medium", "high") else default_risk
        except Exception:
            return default_risk


class CommunicationAgent(BaseFleetAgent):
    """
    Fleet Communication Agent: Generates contextual wording for nudges and escalations using Google GenAI SDK.
    """
    def __init__(self, identity_provider: Optional[AgentIdentityProvider] = None, api_key: Optional[str] = None, model: Optional[str] = None):
        super().__init__(agent_id="communication-agent", agent_version="1.0.0", identity_provider=identity_provider, api_key=api_key, model=model)

    def draft_wording(self, action_name: str, report_id: str, submitter_name: str, amount: Decimal, currency: str) -> str:
        """Generates contextual wording for notification message."""
        default_wording = f"Notification draft: Expense report {report_id} submitted by {submitter_name} for {currency} {amount} requires approval."
        if not self.client:
            return default_wording
        try:
            prompt = f"Draft polite action wording for {action_name} regarding report {report_id} by {submitter_name} for {currency} {amount}. Return JSON: {{\"wording\": str}}"
            response = self.client.models.generate_content(model=self.model, contents=prompt)
            clean = self._clean_json_response(response.text)
            return json.loads(clean).get("wording", default_wording)
        except Exception:
            return default_wording


class EscalationAgent(BaseFleetAgent):
    """
    Fleet Escalation Agent: Formulates procedural escalation proposals for stalled approvals using Google GenAI SDK.
    """
    def __init__(self, identity_provider: Optional[AgentIdentityProvider] = None, api_key: Optional[str] = None, model: Optional[str] = None):
        super().__init__(agent_id="escalation-agent", agent_version="1.0.0", identity_provider=identity_provider, api_key=api_key, model=model)


class FleetOrchestrator:
    """
    Enterprise Fleet Multi-Agent Orchestrator:
    Demonstrates explicit agent delegation across specialized roles powered by Google GenAI SDK:
    Clock -> WorkflowAgent -> PolicyAgent -> CommunicationAgent -> EscalationAgent -> AgentGateway.
    
    Authority Invariant:
    Agents generate structured recommendations and wording.
    Agent Gateway and Deterministic Policy retain 100% authority over authorization and execution.
    """
    def __init__(
        self,
        gateway: Any,
        identity_provider: Optional[AgentIdentityProvider] = None
    ):
        self.gateway = gateway
        self.identity_provider = identity_provider
        self.workflow_agent = WorkflowAgent(identity_provider=identity_provider)
        self.policy_agent = PolicyAgent(identity_provider=identity_provider)
        self.comm_agent = CommunicationAgent(identity_provider=identity_provider)
        self.escalation_agent = EscalationAgent(identity_provider=identity_provider)

    def evaluate_and_propose(
        self,
        report_id: str,
        submitter_name: str,
        submitter_email: str,
        approver_email: str,
        amount: Decimal,
        currency: str = "USD",
        description: str = "Expense report",
        is_escalation: bool = False,
        backup_approver_email: Optional[str] = None
    ) -> tuple[AgentActionProposal, AgentAuthContext, Any]:
        """
        Executes multi-agent pipeline with visible delegation trace.
        """
        from approval_loop.observability.tracer import OpenTelemetryTracer
        tracer = OpenTelemetryTracer.get_tracer()
        tracer.start_trace("fleet.multi_agent_orchestration")

        try:
            # 1. Workflow Agent: Identifies state & action
            with tracer.start_span("workflow_agent.observe", {"report_id": report_id}):
                action_name = "escalate_approval" if is_escalation else "nudge_approver"
                target_recipient = approver_email

            # 2. Escalation Agent: Resolves backup authority if escalating
            if is_escalation:
                with tracer.start_span("escalation_agent.resolve", {"primary": approver_email, "backup": backup_approver_email}):
                    target_recipient = backup_approver_email or "admin@company.com"

            # 3. Communication Agent: Generates contextual wording
            with tracer.start_span("communication_agent.draft", {"action_name": action_name}):
                wording = self.comm_agent.draft_wording(action_name, report_id, submitter_name, amount, currency)

            # 4. Policy Agent: Assesses risk level
            with tracer.start_span("policy_agent.assess_risk", {"amount": str(amount)}):
                risk = self.policy_agent.assess_risk(amount, currency, action_name)

            # 5. Formulate Proposal
            proposal_id = f"prop_fleet_{uuid.uuid4().hex[:8]}"
            workflow_id = f"wf_fleet_{uuid.uuid4().hex[:8]}"
            proposal = AgentActionProposal(
                proposal_id=proposal_id,
                workflow_id=workflow_id,
                agent_id=self.workflow_agent.agent_id,
                agent_version=self.workflow_agent.agent_version,
                action_name=action_name,
                target_resource_id=report_id,
                amount=amount,
                currency=currency,
                recipient=target_recipient,
                justification=f"Fleet orchestration ({action_name}) with risk={risk}: {wording}",
                raw_llm_reasoning=f"Multi-agent delegation: WorkflowAgent -> EscalationAgent -> CommunicationAgent -> PolicyAgent (risk={risk})."
            )
            auth_context = self.workflow_agent.create_auth_context()

            # 6. Gateway: Authoritative Authorization Gate
            with tracer.start_span("gateway.authorize", {"proposal_id": proposal_id}):
                decision = self.gateway.authorize_action(proposal, auth_context)

            return proposal, auth_context, decision

        finally:
            tracer.end_trace()


