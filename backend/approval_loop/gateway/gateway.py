import uuid
import logging
from decimal import Decimal
from typing import Optional, Any
from approval_loop.domain.gateway_models import (
    AgentActionProposal, AgentAuthContext, GatewayDecision, GatewayDecisionEnum, utc_now
)
from approval_loop.domain.models import (
    ActionRecord, ActionType, ActionStatus, ReportStatus, NotificationEnvelope
)
from approval_loop.domain.agent_registry import AgentRegistryService
from approval_loop.identity.auth_provider import AgentIdentityProvider
from approval_loop.guardrails.safety_guardrail import ModelSafetyGuardrail
from approval_loop.policy.policy_engine import PolicyEngine, PolicyDecisionEnum
from approval_loop.memory.memory_bank import MemoryBankService, WorkflowMemoryRecord, WorkflowState
from approval_loop.observability.tracer import OpenTelemetryTracer
from approval_loop.worker.worker import BaseNotificationProvider

logger = logging.getLogger("approval_loop.gateway")

class AgentGateway:
    """
    ApprovalLoop Agent Gateway:
    The central deterministic execution governance gateway for autonomous AI agent fleets.
    
    Invariant: AI proposes. Deterministic policy decides. Infrastructure executes.
    
    Full Gateway Flow:
    Agent Proposal -> Cryptographic Identity Check -> Model Safety Defense ->
    Policy Profile Evaluation -> Deterministic Parameter Check -> Gateway Decision ->
    (If ALLOW: Instant/Async Execution; If REQUIRE_HUMAN_APPROVAL: Workflow Paused; If DENY: Blocked & Audited)
    """
    def __init__(
        self,
        registry: AgentRegistryService,
        identity_provider: AgentIdentityProvider,
        policy_engine: PolicyEngine,
        memory_bank: MemoryBankService,
        worker: BaseNotificationProvider,
        guardrail: Optional[ModelSafetyGuardrail] = None,
        tracer: Optional[OpenTelemetryTracer] = None
    ):
        self.registry = registry
        self.identity_provider = identity_provider
        self.policy_engine = policy_engine
        self.memory_bank = memory_bank
        self.worker = worker
        self.guardrail = guardrail or ModelSafetyGuardrail()
        self.tracer = tracer or OpenTelemetryTracer.get_tracer()

    def authorize_action(
        self,
        proposal: AgentActionProposal,
        auth_context: AgentAuthContext
    ) -> GatewayDecision:
        """
        Ingresses an agent proposal, performs identity, safety, and policy verification,
        and produces an authoritative GatewayDecision.
        """
        decision_id = f"dec_{uuid.uuid4().hex[:10]}"
        action_record_id = f"act_gw_{uuid.uuid4().hex[:10]}"
        
        self.tracer.start_trace("gateway.authorize", trace_id=f"trace_{proposal.proposal_id}")

        try:
            # 1. Zero-Trust Identity Verification
            with self.tracer.start_span("identity.verify", {"agent_id": proposal.agent_id, "action": proposal.action_name}):
                auth_ok, auth_reason, claims = self.identity_provider.verify_agent_request(proposal, auth_context)
                if not auth_ok:
                    logger.warning("Gateway blocked unauthorized agent '%s': %s", proposal.agent_id, auth_reason)
                    decision = GatewayDecision(
                        decision_id=decision_id,
                        proposal_id=proposal.proposal_id,
                        workflow_id=proposal.workflow_id,
                        agent_id=proposal.agent_id,
                        action_name=proposal.action_name,
                        decision=GatewayDecisionEnum.DENY,
                        reason=f"Identity Check Failed: {auth_reason}",
                        policy_version="none",
                        risk_level="critical",
                        identity_verified=False,
                        validation_passed=False,
                        safety_guardrail_passed=True,
                        requires_human_approval=False,
                        action_record_id=action_record_id,
                        details={"auth_reason": auth_reason}
                    )
                    self._record_in_memory(proposal, decision)
                    return decision

            # 2. Model Safety & Prompt Defense (Model Armor)
            with self.tracer.start_span("model_safety.inspect", {"agent_id": proposal.agent_id}):
                safety_res = self.guardrail.inspect_model_output(proposal.justification)
                if not safety_res.passed:
                    logger.warning("Gateway safety guardrail intercepted proposal '%s': %s", proposal.proposal_id, safety_res.reason)
                    decision = GatewayDecision(
                        decision_id=decision_id,
                        proposal_id=proposal.proposal_id,
                        workflow_id=proposal.workflow_id,
                        agent_id=proposal.agent_id,
                        action_name=proposal.action_name,
                        decision=GatewayDecisionEnum.DENY,
                        reason=f"Model Safety Violation: {safety_res.reason}",
                        policy_version="safety-guardrail",
                        risk_level="high",
                        identity_verified=True,
                        validation_passed=False,
                        safety_guardrail_passed=False,
                        requires_human_approval=False,
                        action_record_id=action_record_id,
                        details={"detected_threats": safety_res.detected_threats}
                    )
                    self._record_in_memory(proposal, decision)
                    return decision

            # 3. Deterministic Policy Evaluation
            agent_reg = self.registry.get_agent(proposal.agent_id)
            profile_name = agent_reg.policy_profile if agent_reg else "finance-v3"

            with self.tracer.start_span("policy.evaluate", {"policy_profile": profile_name, "amount": str(proposal.amount)}):
                policy_dec, policy_reason, policy_version = self.policy_engine.evaluate_proposal(proposal, profile_name)

            risk_level = agent_reg.risk_level.value if agent_reg else "medium"

            # 4. Map Decision Outcome
            if policy_dec == PolicyDecisionEnum.ALLOW:
                decision = GatewayDecision(
                    decision_id=decision_id,
                    proposal_id=proposal.proposal_id,
                    workflow_id=proposal.workflow_id,
                    agent_id=proposal.agent_id,
                    action_name=proposal.action_name,
                    decision=GatewayDecisionEnum.ALLOW,
                    reason=policy_reason,
                    policy_version=policy_version,
                    risk_level=risk_level,
                    identity_verified=True,
                    validation_passed=True,
                    safety_guardrail_passed=True,
                    requires_human_approval=False,
                    action_record_id=action_record_id,
                    details={"action": proposal.action_name, "amount": str(proposal.amount), "recipient": proposal.recipient}
                )
                self._record_in_memory(proposal, decision)
                # Automatic execution for low-risk allowed actions
                self._execute_proposal_action(proposal, decision, operator="ApprovalLoop Auto-Executor")

            elif policy_dec == PolicyDecisionEnum.REQUIRE_HUMAN_APPROVAL:
                decision = GatewayDecision(
                    decision_id=decision_id,
                    proposal_id=proposal.proposal_id,
                    workflow_id=proposal.workflow_id,
                    agent_id=proposal.agent_id,
                    action_name=proposal.action_name,
                    decision=GatewayDecisionEnum.REQUIRE_HUMAN_APPROVAL,
                    reason=policy_reason,
                    policy_version=policy_version,
                    risk_level=risk_level,
                    identity_verified=True,
                    validation_passed=True,
                    safety_guardrail_passed=True,
                    requires_human_approval=True,
                    action_record_id=action_record_id,
                    details={"action": proposal.action_name, "amount": str(proposal.amount), "recipient": proposal.recipient}
                )
                self._record_in_memory(proposal, decision)
                # Pause workflow and store in pending queue durably
                self._store_pending_action(action_record_id, proposal, decision)

            else:  # DENY
                decision = GatewayDecision(
                    decision_id=decision_id,
                    proposal_id=proposal.proposal_id,
                    workflow_id=proposal.workflow_id,
                    agent_id=proposal.agent_id,
                    action_name=proposal.action_name,
                    decision=GatewayDecisionEnum.DENY,
                    reason=policy_reason,
                    policy_version=policy_version,
                    risk_level="critical",
                    identity_verified=True,
                    validation_passed=False,
                    safety_guardrail_passed=True,
                    requires_human_approval=False,
                    action_record_id=action_record_id,
                    details={"action": proposal.action_name, "amount": str(proposal.amount), "recipient": proposal.recipient}
                )
                self._record_in_memory(proposal, decision)

            return decision

        finally:
            self.tracer.end_trace()

    def _record_in_memory(self, proposal: AgentActionProposal, decision: GatewayDecision):
        """Persists workflow state and history in Memory Bank."""
        rec = self.memory_bank.get_workflow(proposal.workflow_id)
        if not rec:
            rec = WorkflowMemoryRecord(
                workflow_id=proposal.workflow_id,
                agent_id=proposal.agent_id,
                session_id=proposal.session_id or f"sess_{uuid.uuid4().hex[:8]}",
                state=WorkflowState.RUNNING if decision.decision == GatewayDecisionEnum.ALLOW else (
                    WorkflowState.PAUSED_FOR_APPROVAL if decision.decision == GatewayDecisionEnum.REQUIRE_HUMAN_APPROVAL else WorkflowState.FAILED
                ),
                policy_version=decision.policy_version,
                metadata={"action": proposal.action_name, "target": proposal.target_resource_id}
            )
        rec.action_history.append(proposal.to_dict())
        rec.previous_decisions.append(decision.to_dict())
        self.memory_bank.save_workflow(rec)

    def _store_pending_action(self, action_id: str, proposal: AgentActionProposal, decision: GatewayDecision):
        """Persists pending approval state durably in Memory Bank (survives restarts & distributed nodes)."""
        pending_data = {
            "action_id": action_id,
            "proposal": proposal.to_dict(),
            "decision": decision.to_dict(),
            "status": "pending_human_approval",
            "created_at": utc_now().isoformat(),
        }
        wf = self.memory_bank.get_workflow(proposal.workflow_id)
        if not wf:
            wf = WorkflowMemoryRecord(
                workflow_id=proposal.workflow_id,
                agent_id=proposal.agent_id,
                session_id=proposal.session_id or f"sess_{uuid.uuid4().hex[:8]}",
                state=WorkflowState.PAUSED_FOR_APPROVAL,
                policy_version=decision.policy_version
            )
        wf.metadata["pending_action"] = pending_data
        self.memory_bank.save_workflow(wf)
        self.memory_bank.pause_for_approval(
            workflow_id=proposal.workflow_id,
            action_id=action_id,
            reason=decision.reason,
            policy_version=decision.policy_version,
            proposal_id=proposal.proposal_id
        )

    def list_pending_actions(self) -> list[dict[str, Any]]:
        """Reconstructs pending approval actions from durable Memory Bank storage."""
        paused_workflows = self.memory_bank.list_workflows(state=WorkflowState.PAUSED_FOR_APPROVAL)
        pending = []
        for wf in paused_workflows:
            pending_data = wf.metadata.get("pending_action")
            if pending_data and pending_data.get("status") == "pending_human_approval":
                pending.append(pending_data)
            else:
                proposal_dict = wf.action_history[-1] if wf.action_history else {}
                decision_dict = wf.previous_decisions[-1] if wf.previous_decisions else {}
                action_id = wf.current_action_id or (wf.approval_record.action_id if wf.approval_record else None) or f"act_{wf.workflow_id}"
                pending.append({
                    "action_id": action_id,
                    "proposal": proposal_dict,
                    "decision": decision_dict,
                    "status": "pending_human_approval",
                    "created_at": wf.paused_at.isoformat() if wf.paused_at else wf.created_at.isoformat(),
                })
        return pending

    def approve_action(self, action_id: str, operator: str = "Admin Operator", notes: str = "") -> GatewayDecision:
        """
        Human approval resolution: Atomically claims and resumes workflow, triggering idempotent execution.
        Prevents concurrent or duplicate approvals.
        """
        success, reason, wf = self.memory_bank.claim_and_transition_approval(
            action_id=action_id,
            approve=True,
            operator=operator,
            notes=notes
        )
        if not success:
            raise ValueError(reason)

        pending_data = wf.metadata.get("pending_action", {})
        proposal_dict = pending_data.get("proposal") or (wf.action_history[-1] if wf.action_history else {})
        decision_dict = pending_data.get("decision") or (wf.previous_decisions[-1] if wf.previous_decisions else {})
        
        if not proposal_dict:
            raise ValueError(f"Proposal data for action '{action_id}' not found in workflow memory.")

        proposal = AgentActionProposal(**proposal_dict)

        # Execute side effect
        exec_ok, receipt_id, err = self._execute_proposal_action(proposal, decision_dict, operator=operator)

        # Record immutable approval details in metadata
        if "pending_action" not in wf.metadata:
            wf.metadata["pending_action"] = {}
        wf.metadata["pending_action"]["status"] = "approved_and_executed"
        wf.metadata["pending_action"]["executed_at"] = utc_now().isoformat()
        wf.metadata["pending_action"]["receipt_id"] = receipt_id
        wf.metadata["pending_action"]["approved_by"] = operator
        wf.metadata["pending_action"]["notes"] = notes
        self.memory_bank.save_workflow(wf)

        return GatewayDecision(
            decision_id=f"dec_app_{uuid.uuid4().hex[:8]}",
            proposal_id=proposal.proposal_id,
            workflow_id=proposal.workflow_id,
            agent_id=proposal.agent_id,
            action_name=proposal.action_name,
            decision=GatewayDecisionEnum.ALLOW,
            reason=f"Human Approval Granted by {operator}. Executed with receipt {receipt_id}.",
            policy_version=wf.policy_version or decision_dict.get("policy_version", "finance-v3"),
            risk_level="medium",
            identity_verified=True,
            validation_passed=True,
            safety_guardrail_passed=True,
            requires_human_approval=False,
            action_record_id=action_id,
            details={
                "operator": operator,
                "notes": notes,
                "executed_at": utc_now().isoformat(),
                "receipt_id": receipt_id,
                "proposal_id": proposal.proposal_id
            }
        )

    def reject_action(self, action_id: str, operator: str = "Admin Operator", notes: str = "") -> GatewayDecision:
        """
        Human rejection resolution: Atomically claims and terminates paused workflow with audit record.
        Prevents concurrent or duplicate rejections.
        """
        success, reason, wf = self.memory_bank.claim_and_transition_approval(
            action_id=action_id,
            approve=False,
            operator=operator,
            notes=notes
        )
        if not success:
            raise ValueError(reason)

        pending_data = wf.metadata.get("pending_action", {})
        proposal_dict = pending_data.get("proposal") or (wf.action_history[-1] if wf.action_history else {})
        decision_dict = pending_data.get("decision") or (wf.previous_decisions[-1] if wf.previous_decisions else {})
        
        if not proposal_dict:
            raise ValueError(f"Proposal data for action '{action_id}' not found in workflow memory.")

        proposal = AgentActionProposal(**proposal_dict)

        if "pending_action" not in wf.metadata:
            wf.metadata["pending_action"] = {}
        wf.metadata["pending_action"]["status"] = "rejected_by_human"
        wf.metadata["pending_action"]["rejected_at"] = utc_now().isoformat()
        wf.metadata["pending_action"]["rejected_by"] = operator
        wf.metadata["pending_action"]["notes"] = notes
        self.memory_bank.save_workflow(wf)

        return GatewayDecision(
            decision_id=f"dec_rej_{uuid.uuid4().hex[:8]}",
            proposal_id=proposal.proposal_id,
            workflow_id=proposal.workflow_id,
            agent_id=proposal.agent_id,
            action_name=proposal.action_name,
            decision=GatewayDecisionEnum.DENY,
            reason=f"Human Approval Rejected by {operator}. Notes: {notes or 'No notes provided'}.",
            policy_version=wf.policy_version or decision_dict.get("policy_version", "finance-v3"),
            risk_level="high",
            identity_verified=True,
            validation_passed=True,
            safety_guardrail_passed=True,
            requires_human_approval=False,
            action_record_id=action_id,
            details={
                "operator": operator,
                "notes": notes,
                "rejected_at": utc_now().isoformat(),
                "proposal_id": proposal.proposal_id
            }
        )

    def _execute_proposal_action(
        self,
        proposal: AgentActionProposal,
        decision_dict: Any,
        operator: str = "System"
    ) -> tuple[bool, str | None, str | None]:
        """Dispatches authorized tool side effect via Worker with deduplication."""
        idempotency_key = f"gw:{proposal.workflow_id}:{proposal.action_name}:{proposal.target_resource_id}"
        envelope = NotificationEnvelope(
            report_id=proposal.target_resource_id,
            amount=proposal.amount or Decimal("0.00"),
            currency=proposal.currency,
            recipient=proposal.recipient,
            submitter_name=proposal.agent_id,
            subject=f"Execution Authorized: {proposal.action_name.replace('_', ' ').title()} for {proposal.target_resource_id}",
            body_text=proposal.justification,
            raw_llm_draft=proposal.raw_llm_reasoning
        )
        ok, notif_id, err = self.worker.send(envelope, idempotency_key=idempotency_key)
        
        result_payload = {
            "executed": ok,
            "notification_id": notif_id,
            "operator": operator,
            "error": err,
            "executed_at": utc_now().isoformat()
        }
        if ok:
            self.memory_bank.complete_workflow(proposal.workflow_id, result_payload)
        return ok, notif_id, err
