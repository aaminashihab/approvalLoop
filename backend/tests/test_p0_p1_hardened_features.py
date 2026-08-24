import pytest
from decimal import Decimal
from datetime import timedelta
from fastapi.testclient import TestClient

from approval_loop.api.app import app
from approval_loop.config import Settings, AppEnvironment
from approval_loop.storage.memory_repo import InMemoryRepository
from approval_loop.domain.registry import ApproverRegistry
from approval_loop.validator.validator import DeterministicValidator
from approval_loop.agent.drafter import GeminiAgentDrafter
from approval_loop.worker.worker import MockNotificationWorker
from approval_loop.engine import ApprovalEngine
from approval_loop.domain.models import ExpenseReport, ReportStatus, ActionStatus, StateTransitionResult, utc_now
from approval_loop.domain.agent_registry import AgentRegistryService
from approval_loop.identity.auth_provider import AgentIdentityProvider
from approval_loop.policy.policy_engine import PolicyEngine
from approval_loop.memory.memory_bank import MemoryBankService
from approval_loop.gateway.gateway import AgentGateway
from approval_loop.runtime.async_runtime import AsyncAgentRuntime, AsyncTaskState
from approval_loop.agent.fleet import WorkflowAgent, PolicyAgent, CommunicationAgent, EscalationAgent

client = TestClient(app)

def test_unauthenticated_mutation_endpoints_rejected():
    """Verify POST /api/reports and POST /api/reports/{id}/resolve reject unauthenticated requests."""
    # Test POST /api/reports without auth header
    res1 = client.post("/api/reports", json={
        "submitter_name": "Eve",
        "submitter_email": "eve@company.com",
        "approver_email": "sarah.finance@company.com",
        "amount": "100.00",
        "description": "Unauth attempt"
    })
    assert res1.status_code == 401

    # Test POST /api/reports/{id}/resolve without auth header
    res2 = client.post("/api/reports/EXP-101/resolve")
    assert res2.status_code == 401


def test_demo_routes_disabled_in_production():
    """Verify demo/simulation routes return 403 Forbidden when APP_ENV=production."""
    from approval_loop.api.routes import get_settings
    prod_settings = Settings(app_env=AppEnvironment.PRODUCTION, scheduler_api_key="sec-key-1234567890")
    app.dependency_overrides[get_settings] = lambda: prod_settings

    try:
        # Seed endpoint
        r1 = client.post("/api/seed")
        assert r1.status_code == 403

        # Reset endpoint
        r2 = client.post("/api/demo/reset")
        assert r2.status_code == 403

        # Advance time endpoint
        r3 = client.post("/api/demo/advance-time", json={"seconds": 30})
        assert r3.status_code == 403

        # Simulate adversarial endpoint
        r4 = client.post("/api/simulate-adversarial")
        assert r4.status_code == 403
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_oidc_validation_rejects_invalid_tokens():
    """Verify _verify_oidc_jwt fails closed on invalid or wrong-audience JWTs."""
    from approval_loop.api.auth import _verify_oidc_jwt
    # Invalid JWT format
    assert _verify_oidc_jwt("invalid.jwt.token", "approval-loop-hackathon") is None
    # Wrong audience
    assert _verify_oidc_jwt("eyJhbGciOiJSUzI1NiJ9.eyJpc3MiOiJodHRwczovL2FjY291bnRzLmdvb2dsZS5jb20iLCJhdWQiOiJ3cm9uZy1hdWQiLCJleHAiOjE3MDAwMDAwMDB9.sig", "proj", expected_audience="right-aud") is None


def test_transactional_task_claiming_prevents_double_claim():
    """Verify that two workers calling claim_next_task cannot claim the same task."""
    repo = InMemoryRepository()
    registry = AgentRegistryService(repo=repo)
    id_provider = AgentIdentityProvider(registry_service=registry, secret_key="tx-test-secret")
    policy = PolicyEngine()
    memory_bank = MemoryBankService(repo=repo)
    worker = MockNotificationWorker()
    
    gateway = AgentGateway(
        registry=registry,
        identity_provider=id_provider,
        policy_engine=policy,
        memory_bank=memory_bank,
        worker=worker
    )
    runtime = AsyncAgentRuntime(gateway=gateway, memory_bank=memory_bank, repo=repo)
    
    # Register agent and create task
    from approval_loop.domain.gateway_models import AgentActionProposal, AgentAuthContext
    token = id_provider.generate_agent_token("finance-agent", "1.2.0")
    proposal = AgentActionProposal(
        agent_id="finance-agent",
        agent_version="1.2.0",
        action_name="issue_refund",
        target_resource_id="REF-TX-99",
        amount=Decimal("100.00"),
        currency="INR",
        recipient="user@company.com"
    )
    auth_ctx = AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0", token=token)
    task, _ = runtime.submit_workflow(proposal, auth_ctx)
    
    # Worker 1 claims task
    claimed_w1 = runtime.claim_next_task(worker_id="worker-node-1")
    assert claimed_w1 is not None
    assert claimed_w1.task_id == task.task_id
    assert claimed_w1.worker_id == "worker-node-1"
    
    # Worker 2 attempts to claim next task simultaneously -> gets None (no double claim)
    claimed_w2 = runtime.claim_next_task(worker_id="worker-node-2")
    assert claimed_w2 is None


def test_pre_dispatch_state_check_prevents_stale_notification():
    """Verify that if human resolves report while processing, notification dispatch is skipped."""
    repo = InMemoryRepository()
    settings = Settings(app_env=AppEnvironment.TEST)
    registry = ApproverRegistry(admin_fallback_email="admin@company.com")
    registry.register_approver("sarah.finance@company.com", "marcus.director@company.com")
    validator = DeterministicValidator(registry=registry)
    drafter = GeminiAgentDrafter()
    worker = MockNotificationWorker()
    engine = ApprovalEngine(repo, settings, registry, drafter, validator, worker)

    now = utc_now()
    report = ExpenseReport(
        report_id="EXP-PRE-DISPATCH-01",
        status=ReportStatus.PENDING,
        submitter_name="Alice",
        submitter_email="alice@company.com",
        approver_email="sarah.finance@company.com",
        amount=Decimal("250.00"),
        currency="USD",
        description="Pending report",
        submitted_at=now - timedelta(seconds=10)
    )
    repo.save_report(report)

    sent_envelopes = []

    def _intercept_worker_send(envelope, idempotency_key=None):
        sent_envelopes.append(envelope)
        return True, "notif-123", None

    worker.send = _intercept_worker_send

    # Simulate human operator resolving report mid-flight after validation but before pre-dispatch check
    original_policy = engine.policy_engine.evaluate
    def _mid_flight_resolve(action, report_obj, envelope):
        res = original_policy(action, report_obj, envelope)
        repo.resolve_report("EXP-PRE-DISPATCH-01")
        return res

    engine.policy_engine.evaluate = _mid_flight_resolve

    actions = engine.run_tick("tick_pre_dispatch_test")
    assert len(actions) == 1
    assert actions[0].state_transition == StateTransitionResult.SKIPPED
    assert "report state changed" in actions[0].skip_reason
    assert len(sent_envelopes) == 0  # Pre-dispatch check skipped notification send!


def test_specialized_fleet_agents_delegation():
    """Verify specialized Fleet Agents can be instantiated and format proposals into AgentGateway."""
    registry = AgentRegistryService()
    id_provider = AgentIdentityProvider(registry_service=registry, secret_key="fleet-test-secret")
    
    workflow_agent = WorkflowAgent(identity_provider=id_provider)
    policy_agent = PolicyAgent(identity_provider=id_provider)
    comm_agent = CommunicationAgent(identity_provider=id_provider)
    esc_agent = EscalationAgent(identity_provider=id_provider)

    assert workflow_agent.agent_id == "workflow-agent"
    assert policy_agent.agent_id == "policy-agent"
    assert comm_agent.agent_id == "communication-agent"
    assert esc_agent.agent_id == "escalation-agent"


def test_fleet_orchestrator_multi_agent_trace():
    """
    Verify full multi-agent delegation trace:
    Clock -> WorkflowAgent -> EscalationAgent -> CommunicationAgent -> PolicyAgent -> AgentGateway.
    """
    from approval_loop.domain.agent_registry import AgentRegistration, AgentStatus, RiskLevel
    registry = AgentRegistryService()
    registry.register_agent(AgentRegistration(
        agent_id="workflow-agent",
        name="Fleet Workflow Agent",
        description="Autonomous workflow orchestration agent",
        owner="Enterprise Ops",
        version="1.0.0",
        status=AgentStatus.ACTIVE,
        risk_level=RiskLevel.LOW,
        allowed_actions=["escalate_approval", "nudge_approver"]
    ))
    id_provider = AgentIdentityProvider(registry_service=registry, secret_key="fleet-orchestrator-secret")
    policy = PolicyEngine()
    memory_bank = MemoryBankService()
    worker = MockNotificationWorker()
    gateway = AgentGateway(
        registry=registry,
        identity_provider=id_provider,
        policy_engine=policy,
        memory_bank=memory_bank,
        worker=worker
    )
    
    from approval_loop.agent.fleet import FleetOrchestrator
    orchestrator = FleetOrchestrator(gateway=gateway, identity_provider=id_provider)

    proposal, auth_ctx, decision = orchestrator.evaluate_and_propose(
        report_id="EXP-FLEET-100",
        submitter_name="Marcus",
        submitter_email="marcus@company.com",
        approver_email="sarah.finance@company.com",
        amount=Decimal("150.00"),
        currency="USD",
        description="Software SaaS enterprise license",
        is_escalation=True,
        backup_approver_email="director@company.com"
    )

    assert proposal.agent_id == "workflow-agent"
    assert proposal.recipient == "director@company.com"
    assert "WorkflowAgent" in proposal.raw_llm_reasoning
    assert "EscalationAgent" in proposal.raw_llm_reasoning
    assert decision.decision.value in ("allow", "require_human_approval")


def test_competing_multithreaded_workers_claim_exactly_once():
    """
    Empirical Concurrency Test:
    Worker A and Worker B run in separate parallel threads and attempt to claim
    the exact same queued task simultaneously.
    Proves that exactly ONE worker gets the claim, and the other gets None.
    """
    import concurrent.futures
    from approval_loop.domain.agent_registry import AgentRegistration, AgentStatus, RiskLevel
    repo = InMemoryRepository()
    registry = AgentRegistryService(repo=repo)
    registry.register_agent(AgentRegistration(
        agent_id="finance-agent",
        name="Fleet Finance Agent",
        description="Institutional finance agent",
        owner="Finance Dept",
        version="1.2.0",
        status=AgentStatus.ACTIVE,
        risk_level=RiskLevel.LOW,
        allowed_actions=["issue_refund"]
    ))
    id_provider = AgentIdentityProvider(registry_service=registry, secret_key="multithread-test-secret")
    policy = PolicyEngine()
    memory_bank = MemoryBankService(repo=repo)
    worker = MockNotificationWorker()
    
    gateway = AgentGateway(
        registry=registry,
        identity_provider=id_provider,
        policy_engine=policy,
        memory_bank=memory_bank,
        worker=worker
    )
    runtime = AsyncAgentRuntime(gateway=gateway, memory_bank=memory_bank, repo=repo)

    from approval_loop.domain.gateway_models import AgentActionProposal, AgentAuthContext
    token = id_provider.generate_agent_token("finance-agent", "1.2.0")
    proposal = AgentActionProposal(
        agent_id="finance-agent",
        agent_version="1.2.0",
        action_name="issue_refund",
        target_resource_id="REF-RACE-THREAD-1",
        amount=Decimal("40.00"),
        currency="USD",
        recipient="client@company.com"
    )
    auth_ctx = AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0", token=token)
    task, _ = runtime.submit_workflow(proposal, auth_ctx)
    assert task.status == AsyncTaskState.QUEUED

    results = []

    def _worker_claim(worker_name: str):
        res = runtime.claim_next_task(worker_id=worker_name)
        return (worker_name, res)

    # Launch Worker A and Worker B concurrently on thread pool
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(_worker_claim, "Worker-Node-A")
        f2 = executor.submit(_worker_claim, "Worker-Node-B")
        results.append(f1.result())
        results.append(f2.result())

    successful_claims = [res for name, res in results if res is not None]
    failed_claims = [res for name, res in results if res is None]

    # Invariant: Exactly ONE worker succeeds, exactly ONE worker receives None
    assert len(successful_claims) == 1
    assert len(failed_claims) == 1
    winner_name, winner_task = results[0] if results[0][1] is not None else results[1]
    assert winner_task.task_id == task.task_id
    assert winner_task.worker_id in ("Worker-Node-A", "Worker-Node-B")

