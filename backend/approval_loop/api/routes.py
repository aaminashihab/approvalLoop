import uuid
from decimal import Decimal
from datetime import timedelta
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Header, status
from pydantic import BaseModel, Field

from approval_loop.domain.models import ExpenseReport, ReportStatus, NotificationEnvelope, utc_now
from approval_loop.domain.agent_registry import AgentRegistration, AgentStatus, AgentRegistryService, RiskLevel
from approval_loop.domain.gateway_models import AgentActionProposal, AgentAuthContext, GatewayDecision
from approval_loop.domain.agbom import get_agbom_inventory
from approval_loop.engine import ApprovalEngine
from approval_loop.config import Settings, AppEnvironment
from approval_loop.gateway.gateway import AgentGateway
from approval_loop.memory.memory_bank import MemoryBankService
from approval_loop.runtime.async_runtime import AsyncAgentRuntime
from approval_loop.agent.fleet import FinanceAgent, SupportAgent, SalesAgent
from approval_loop.api.auth import verify_scheduler_auth, verify_admin_auth, verify_operator_auth

router = APIRouter(prefix="/api")

_engine_instance: Optional[ApprovalEngine] = None
_settings_instance: Optional[Settings] = None
_gateway_instance: Optional[AgentGateway] = None
_registry_service_instance: Optional[AgentRegistryService] = None
_memory_bank_instance: Optional[MemoryBankService] = None
_runtime_instance: Optional[AsyncAgentRuntime] = None
_finance_agent_instance: Optional[FinanceAgent] = None
_support_agent_instance: Optional[SupportAgent] = None
_sales_agent_instance: Optional[SalesAgent] = None

def set_engine_instance(engine: ApprovalEngine):
    global _engine_instance
    _engine_instance = engine

def set_settings_instance(settings: Settings):
    global _settings_instance
    _settings_instance = settings

def set_gateway_instance(gateway: AgentGateway):
    global _gateway_instance
    _gateway_instance = gateway

def set_registry_service_instance(registry: AgentRegistryService):
    global _registry_service_instance
    _registry_service_instance = registry

def set_memory_bank_instance(memory_bank: MemoryBankService):
    global _memory_bank_instance
    _memory_bank_instance = memory_bank

def set_runtime_instance(runtime: AsyncAgentRuntime):
    global _runtime_instance
    _runtime_instance = runtime

def set_fleet_instances(finance: FinanceAgent, support: SupportAgent, sales: SalesAgent):
    global _finance_agent_instance, _support_agent_instance, _sales_agent_instance
    _finance_agent_instance = finance
    _support_agent_instance = support
    _sales_agent_instance = sales

def get_engine() -> ApprovalEngine:
    if _engine_instance is None:
        raise RuntimeError("ApprovalEngine not initialized")
    return _engine_instance

def get_settings() -> Settings:
    if _settings_instance is None:
        raise RuntimeError("Settings not initialized")
    return _settings_instance

def get_gateway() -> AgentGateway:
    if _gateway_instance is None:
        raise RuntimeError("AgentGateway not initialized")
    return _gateway_instance

def get_registry_service() -> AgentRegistryService:
    if _registry_service_instance is None:
        raise RuntimeError("AgentRegistryService not initialized")
    return _registry_service_instance

def get_memory_bank() -> MemoryBankService:
    if _memory_bank_instance is None:
        raise RuntimeError("MemoryBankService not initialized")
    return _memory_bank_instance

def get_runtime() -> AsyncAgentRuntime:
    if _runtime_instance is None:
        raise RuntimeError("AsyncAgentRuntime not initialized")
    return _runtime_instance

# Request / Response Schemas
class CreateReportRequest(BaseModel):
    report_id: Optional[str] = None
    submitter_name: str
    submitter_email: str
    approver_email: str
    backup_approver_email: Optional[str] = None
    amount: Decimal
    currency: str = "USD"
    description: str

class AdvanceTimeRequest(BaseModel):
    seconds: int = 35

class AgentProposalIngressRequest(BaseModel):
    proposal: AgentActionProposal
    auth_context: AgentAuthContext

class HumanApprovalRequest(BaseModel):
    operator: str = "Admin Operator"
    notes: str = ""

class AgentStatusUpdateRequest(BaseModel):
    status: AgentStatus

# ==========================================
# 1. CORE & OBSERVABILITY ENDPOINTS
# ==========================================

@router.get("/agbom")
def get_agbom():
    """Returns runtime Agent Bill of Materials (AgBOM) inventory."""
    return get_agbom_inventory()

@router.get("/traces")
def get_traces(limit: int = Query(20, ge=1, le=100), engine: ApprovalEngine = Depends(get_engine)):
    """Returns recent OpenTelemetry-compatible execution spans and trace records."""
    return engine.tracer.get_recent_traces(limit=limit)

@router.get("/metrics")
def get_metrics(engine: ApprovalEngine = Depends(get_engine)):
    """Returns live, computed proof-of-autonomy metrics."""
    return engine.get_autonomy_metrics().model_dump()

# ==========================================
# 2. AGENT REGISTRY ENDPOINTS (Requirement 4)
# ==========================================

@router.get("/registry/agents")
def list_agents(registry: AgentRegistryService = Depends(get_registry_service)):
    """Lists all registered institutional agents in the enterprise fleet."""
    return [a.to_dict() for a in registry.list_agents()]

@router.get("/registry/agents/{agent_id}")
def get_agent(agent_id: str, registry: AgentRegistryService = Depends(get_registry_service)):
    agent = registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found in registry.")
    return agent.to_dict()

@router.post("/registry/agents")
def register_agent(
    agent_data: AgentRegistration,
    registry: AgentRegistryService = Depends(get_registry_service),
    auth: bool = Depends(verify_admin_auth)
):
    """Registers or updates an institutional agent specification."""
    registered = registry.register_agent(agent_data)
    return {"message": "Agent registered successfully", "agent": registered.to_dict()}

@router.post("/registry/agents/{agent_id}/status")
def update_agent_status(
    agent_id: str,
    req: AgentStatusUpdateRequest,
    registry: AgentRegistryService = Depends(get_registry_service),
    auth: bool = Depends(verify_admin_auth)
):
    """Enables or disables an agent in the registry."""
    updated = registry.update_agent_status(agent_id, req.status)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found.")
    return {"message": f"Agent status updated to '{req.status.value}'", "agent": updated.to_dict()}

# ==========================================
# 3. AGENT GATEWAY & HUMAN-IN-THE-LOOP (Requirements 6, 7, 9)
# ==========================================

@router.post("/gateway/propose")
def propose_agent_action(
    req: AgentProposalIngressRequest,
    gateway: AgentGateway = Depends(get_gateway)
):
    """
    Main Gateway Ingress:
    Agent -> Gateway -> Identity Check -> Policy Check -> Deterministic Validator -> Gateway Decision.
    """
    decision = gateway.authorize_action(req.proposal, req.auth_context)
    return decision.to_dict()

@router.get("/gateway/actions/pending")
def list_pending_gateway_actions(
    gateway: AgentGateway = Depends(get_gateway),
    operator_principal: str = Depends(verify_operator_auth)
):
    """Returns actions awaiting human-in-the-loop approval."""
    return gateway.list_pending_actions()

@router.post("/gateway/actions/{action_id}/approve")
def approve_gateway_action(
    action_id: str,
    req: HumanApprovalRequest,
    gateway: AgentGateway = Depends(get_gateway),
    operator_principal: str = Depends(verify_operator_auth)
):
    """Human approval sign-off: resumes paused workflow and triggers execution."""
    try:
        decision = gateway.approve_action(action_id, operator=operator_principal, notes=req.notes)
        return {"message": "Action approved and dispatched", "decision": decision.to_dict()}
    except ValueError as e:
        err_msg = str(e)
        if "already" in err_msg.lower():
            raise HTTPException(status_code=409, detail=err_msg)
        raise HTTPException(status_code=404, detail=err_msg)

@router.post("/gateway/actions/{action_id}/reject")
def reject_gateway_action(
    action_id: str,
    req: HumanApprovalRequest,
    gateway: AgentGateway = Depends(get_gateway),
    operator_principal: str = Depends(verify_operator_auth)
):
    """Human rejection: terminates workflow with audit record."""
    try:
        decision = gateway.reject_action(action_id, operator=operator_principal, notes=req.notes)
        return {"message": "Action rejected", "decision": decision.to_dict()}
    except ValueError as e:
        err_msg = str(e)
        if "already" in err_msg.lower():
            raise HTTPException(status_code=409, detail=err_msg)
        raise HTTPException(status_code=404, detail=err_msg)

# ==========================================
# 4. MEMORY BANK & ASYNC RUNTIME (Requirements 8, 9)
# ==========================================

@router.get("/memory/workflows")
def list_workflows(
    agent_id: Optional[str] = Query(None),
    memory_bank: MemoryBankService = Depends(get_memory_bank)
):
    workflows = memory_bank.list_workflows(agent_id=agent_id)
    return [w.to_dict() for w in workflows]

@router.get("/memory/workflows/{workflow_id}")
def get_workflow_memory(
    workflow_id: str,
    memory_bank: MemoryBankService = Depends(get_memory_bank)
):
    wf = memory_bank.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found in Memory Bank.")
    return wf.to_dict()

# ==========================================
# 5. CRITICAL DEMO SCENARIO ENDPOINTS (Requirement 19)
# ==========================================

@router.post("/demo/scenario-a")
def trigger_scenario_a(
    gateway: AgentGateway = Depends(get_gateway),
    settings: Settings = Depends(get_settings)
):
    """
    Case A: Finance Agent requests Refund of ₹2,000 ($20).
    Expected: ALLOW -> Automatic Execution.
    """
    if settings.app_env == AppEnvironment.PRODUCTION:
        raise HTTPException(status_code=403, detail="Demo scenarios disabled in PRODUCTION environment.")

    if not _finance_agent_instance:
        raise HTTPException(status_code=500, detail="Finance Agent not initialized.")

    proposal, auth_ctx = _finance_agent_instance.propose_refund(
        refund_id=f"REF-A-{uuid.uuid4().hex[:4].upper()}",
        customer_email="alice.customer@client.com",
        amount=Decimal("2000.00"),
        currency="INR",
        reason="Low-value return on item #4412"
    )
    decision = gateway.authorize_action(proposal, auth_ctx)
    return {
        "scenario": "Case A: Low-Risk Action (< ₹5,000 / $50)",
        "expected_outcome": "ALLOW (Automatic Execution)",
        "proposal": proposal.to_dict(),
        "auth_context": auth_ctx.to_dict(),
        "decision": decision.to_dict()
    }

@router.post("/demo/scenario-b")
def trigger_scenario_b(
    gateway: AgentGateway = Depends(get_gateway),
    settings: Settings = Depends(get_settings)
):
    """
    Case B: Finance Agent requests Refund of ₹20,000 ($200).
    Expected: REQUIRE_HUMAN_APPROVAL -> Workflow pauses in Memory Bank, awaits Dashboard approval.
    """
    if settings.app_env == AppEnvironment.PRODUCTION:
        raise HTTPException(status_code=403, detail="Demo scenarios disabled in PRODUCTION environment.")

    if not _finance_agent_instance:
        raise HTTPException(status_code=500, detail="Finance Agent not initialized.")

    proposal, auth_ctx = _finance_agent_instance.propose_refund(
        refund_id=f"REF-B-{uuid.uuid4().hex[:4].upper()}",
        customer_email="bob.customer@client.com",
        amount=Decimal("20000.00"),
        currency="INR",
        reason="Mid-value subscription dispute on enterprise plan"
    )
    decision = gateway.authorize_action(proposal, auth_ctx)
    return {
        "scenario": "Case B: Medium-Risk Action (₹5,000 - ₹25,000 / $50 - $250)",
        "expected_outcome": "REQUIRE_HUMAN_APPROVAL (Workflow Paused)",
        "proposal": proposal.to_dict(),
        "auth_context": auth_ctx.to_dict(),
        "decision": decision.to_dict(),
        "pending_actions": gateway.list_pending_actions()
    }

@router.post("/demo/scenario-c")
def trigger_scenario_c(
    gateway: AgentGateway = Depends(get_gateway),
    settings: Settings = Depends(get_settings)
):
    """
    Case C: Finance Agent requests Refund of ₹100,000 ($1,000).
    Expected: DENY -> Even if Gemini proposes it, ApprovalLoop's deterministic policy rejects it.
    """
    if settings.app_env == AppEnvironment.PRODUCTION:
        raise HTTPException(status_code=403, detail="Demo scenarios disabled in PRODUCTION environment.")

    if not _finance_agent_instance:
        raise HTTPException(status_code=500, detail="Finance Agent not initialized.")

    proposal, auth_ctx = _finance_agent_instance.propose_refund(
        refund_id=f"REF-C-{uuid.uuid4().hex[:4].upper()}",
        customer_email="carlos.customer@client.com",
        amount=Decimal("100000.00"),
        currency="INR",
        reason="High-value settlement demand"
    )
    decision = gateway.authorize_action(proposal, auth_ctx)
    return {
        "scenario": "Case C: High-Risk Financial Action (> ₹25,000 / $250)",
        "expected_outcome": "DENY (Deterministic Policy Enforced)",
        "proposal": proposal.to_dict(),
        "auth_context": auth_ctx.to_dict(),
        "decision": decision.to_dict()
    }

# ==========================================
# 6. EXPENSE REPORTS & AUTONOMOUS ENGINE (Preserved)
# ==========================================

@router.get("/reports")
def list_reports(engine: ApprovalEngine = Depends(get_engine)):
    reports = engine.repo.list_all_reports()
    return [r.to_dict() for r in reports]

@router.post("/reports")
def create_report(req: CreateReportRequest, engine: ApprovalEngine = Depends(get_engine)):
    report_id = req.report_id or f"EXP-{uuid.uuid4().hex[:4].upper()}"
    report = ExpenseReport(
        report_id=report_id,
        submitter_name=req.submitter_name,
        submitter_email=req.submitter_email,
        approver_email=req.approver_email,
        backup_approver_email=req.backup_approver_email,
        amount=req.amount,
        currency=req.currency,
        description=req.description,
        submitted_at=utc_now()
    )
    engine.repo.save_report(report)
    return {"message": "Report created", "report": report.to_dict()}

@router.post("/reports/{report_id}/resolve")
def resolve_report(report_id: str, engine: ApprovalEngine = Depends(get_engine)):
    report = engine.repo.resolve_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"message": "Report resolved", "report": report.to_dict()}

@router.get("/actions")
def list_actions(engine: ApprovalEngine = Depends(get_engine)):
    actions = engine.repo.list_all_actions()
    return [a.to_dict() for a in actions]

@router.post("/tick")
def trigger_tick(
    tick_id: Optional[str] = Query(None),
    engine: ApprovalEngine = Depends(get_engine),
    settings: Settings = Depends(get_settings),
    auth: bool = Depends(verify_scheduler_auth)
):
    processed = engine.run_tick(tick_id=tick_id)
    return {
        "tick_id": tick_id or "tick_auto",
        "processed_count": len(processed),
        "actions": [a.to_dict() for a in processed]
    }

@router.post("/seed")
def seed_demo_data(engine: ApprovalEngine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    now = utc_now()
    demo_reports = [
        ExpenseReport(
            report_id="EXP-101",
            status=ReportStatus.PENDING,
            submitter_name="Alice Chen",
            submitter_email="alice.chen@company.com",
            approver_email="sarah.finance@company.com",
            backup_approver_email="marcus.director@company.com",
            amount=Decimal("150.00"),
            currency="USD",
            description="Client lunch meeting catering",
            submitted_at=now
        ),
        ExpenseReport(
            report_id="EXP-102",
            status=ReportStatus.PENDING,
            submitter_name="Bob Miller",
            submitter_email="bob.miller@company.com",
            approver_email="sarah.finance@company.com",
            backup_approver_email="marcus.director@company.com",
            amount=Decimal("1250.00"),
            currency="USD",
            description="Q3 Cloud Infrastructure annual license",
            submitted_at=now - timedelta(seconds=settings.thresholds.nudge_threshold_seconds + 5)
        ),
        ExpenseReport(
            report_id="EXP-103",
            status=ReportStatus.NUDGED,
            submitter_name="Carlos Gomez",
            submitter_email="carlos.gomez@company.com",
            approver_email="sarah.finance@company.com",
            backup_approver_email="marcus.director@company.com",
            amount=Decimal("3400.00"),
            currency="USD",
            description="Offsite workshop conference venue",
            submitted_at=now - timedelta(seconds=settings.thresholds.nudge_threshold_seconds + settings.thresholds.escalation_threshold_seconds + 20),
            last_nudged_at=now - timedelta(seconds=settings.thresholds.escalation_threshold_seconds + 10)
        ),
        ExpenseReport(
            report_id="EXP-104",
            status=ReportStatus.RESOLVED,
            submitter_name="Diana Prince",
            submitter_email="diana.prince@company.com",
            approver_email="sarah.finance@company.com",
            backup_approver_email="marcus.director@company.com",
            amount=Decimal("520.00"),
            currency="USD",
            description="Team ergonomic monitors and peripherals",
            submitted_at=now - timedelta(seconds=120),
            resolved_at=now - timedelta(seconds=60)
        ),
        ExpenseReport(
            report_id="EXP-105",
            status=ReportStatus.NUDGED,
            submitter_name="Evan Wright",
            submitter_email="evan.wright@company.com",
            approver_email="sarah.finance@company.com",
            backup_approver_email=None,
            amount=Decimal("890.00"),
            currency="USD",
            description="Emergency travel flight rebooking",
            submitted_at=now - timedelta(seconds=200),
            last_nudged_at=now - timedelta(seconds=settings.thresholds.escalation_threshold_seconds + 10)
        ),
    ]

    for r in demo_reports:
        engine.repo.save_report(r)

    return {"message": "Seeded 5 demo expense reports", "count": len(demo_reports)}

@router.post("/demo/advance-time")
def advance_time(req: AdvanceTimeRequest, engine: ApprovalEngine = Depends(get_engine)):
    reports = engine.repo.list_all_reports()
    updated = []
    delta = timedelta(seconds=req.seconds)
    for r in reports:
        r.submitted_at -= delta
        if r.last_nudged_at:
            r.last_nudged_at -= delta
        engine.repo.save_report(r)
        updated.append(r.report_id)
    return {"message": f"Advanced time by {req.seconds}s for {len(updated)} reports", "updated": updated}

@router.post("/simulate-adversarial")
def simulate_adversarial(engine: ApprovalEngine = Depends(get_engine)):
    now = utc_now()
    report_id = f"EXP-ADV-{uuid.uuid4().hex[:4].upper()}"
    report = ExpenseReport(
        report_id=report_id,
        status=ReportStatus.PENDING,
        submitter_name="Adversarial Test Submitter",
        submitter_email="submitter@company.com",
        approver_email="sarah.finance@company.com",
        amount=Decimal("750.00"),
        currency="USD",
        description="Software renewal",
        submitted_at=now - timedelta(seconds=60)
    )
    engine.repo.save_report(report)

    poisoned_envelope = NotificationEnvelope(
        report_id=report_id,
        amount=Decimal("99999.00"),
        currency="USD",
        recipient="unauthorized.attacker@external.com",
        submitter_name="Adversarial Test Submitter",
        subject="Action Required",
        body_text="Please approve immediately.",
        raw_llm_draft="Please approve immediately."
    )

    actions = engine.run_tick(
        tick_id=f"tick_adv_{report_id}",
        injected_adversarial_envelope=poisoned_envelope
    )

    return {
        "scenario": "Safety Demonstration: Deterministic Validator Blocks Hallucination",
        "tagline": "The model can propose. It cannot authorize.",
        "report_id": report_id,
        "actions": [a.to_dict() for a in actions]
    }

@router.post("/simulate-race")
def simulate_race_condition(engine: ApprovalEngine = Depends(get_engine)):
    now = utc_now()
    report_id = f"EXP-RACE-{uuid.uuid4().hex[:4].upper()}"
    report = ExpenseReport(
        report_id=report_id,
        status=ReportStatus.PENDING,
        submitter_name="Race Test Submitter",
        submitter_email="submitter@company.com",
        approver_email="sarah.finance@company.com",
        amount=Decimal("999.00"),
        currency="USD",
        description="Race condition simulation expense",
        submitted_at=now - timedelta(seconds=60)
    )
    engine.repo.save_report(report)

    def _race_resolve(envelope):
        engine.repo.resolve_report(report_id)

    original_callback = engine.worker.on_send_callback
    engine.worker.on_send_callback = _race_resolve

    try:
        actions = engine.run_tick(tick_id=f"tick_race_{report_id}")
    finally:
        engine.worker.on_send_callback = original_callback

    final_report = engine.repo.get_report(report_id)
    return {
        "scenario": "Scenario 13 — Race Condition Guard",
        "report_id": report_id,
        "final_report_status": final_report.status.value if final_report else None,
        "actions": [a.to_dict() for a in actions]
    }

@router.post("/simulate-notification-failure")
def simulate_notification_failure(engine: ApprovalEngine = Depends(get_engine)):
    now = utc_now()
    report_id = f"EXP-FAIL-{uuid.uuid4().hex[:4].upper()}"
    report = ExpenseReport(
        report_id=report_id,
        status=ReportStatus.PENDING,
        submitter_name="Retry Test Submitter",
        submitter_email="submitter@company.com",
        approver_email="sarah.finance@company.com",
        amount=Decimal("450.00"),
        currency="USD",
        description="Software SaaS license",
        submitted_at=now - timedelta(seconds=60)
    )
    engine.repo.save_report(report)

    if hasattr(engine.worker, "simulate_failure"):
        engine.worker.simulate_failure = True

    try:
        failed_actions = engine.run_tick(tick_id=f"tick_fail_{report_id}")
    finally:
        if hasattr(engine.worker, "simulate_failure"):
            engine.worker.simulate_failure = False

    return {
        "scenario": "Fault Tolerance — Provider Timeout & Exponential Retry",
        "report_id": report_id,
        "actions": [a.to_dict() for a in failed_actions],
        "message": "Action marked FAILED with retry backoff timestamp. Retry will recover without duplicate dispatch."
    }

@router.post("/demo/reset")
def reset_demo(engine: ApprovalEngine = Depends(get_engine), settings: Settings = Depends(get_settings)):
    seed_res = seed_demo_data(engine, settings)
    return {"message": "Demo state reset successfully", "seeded": seed_res}
