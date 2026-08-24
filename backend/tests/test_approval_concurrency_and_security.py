import pytest
import concurrent.futures
from decimal import Decimal
from fastapi import HTTPException
from fastapi.testclient import TestClient

from approval_loop.config import Settings, AppEnvironment
from approval_loop.domain.agent_registry import AgentRegistryService
from approval_loop.domain.gateway_models import AgentActionProposal, AgentAuthContext, GatewayDecisionEnum
from approval_loop.identity.auth_provider import AgentIdentityProvider
from approval_loop.guardrails.safety_guardrail import ModelSafetyGuardrail
from approval_loop.policy.policy_engine import PolicyEngine, PolicyDecisionEnum
from approval_loop.memory.memory_bank import MemoryBankService, WorkflowState
from approval_loop.worker.worker import MockNotificationProvider
from approval_loop.gateway.gateway import AgentGateway
from approval_loop.api.auth import verify_operator_auth, verify_scheduler_auth, verify_admin_auth
from approval_loop.api.app import app

def test_jwt_verification_fails_closed():
    """Verify that unverified / bad JWT signatures fail closed and are never trusted."""
    settings = Settings(
        app_env=AppEnvironment.PRODUCTION,
        scheduler_api_key="prod-secret-123",
        agent_identity_secret="prod-identity-secret-123",
        admin_fallback_email="admin@company.com",
        gemini_api_key="sk-real-gemini-key",
        google_cloud_project="my-prod-project"
    )
    
    # 1. Fake / forged JWT payload without valid Google signature
    forged_jwt = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2FjY291bnRzLmdvb2dsZS5jb20iLCJzdWIiOiIxMjM0NTY3ODkwIiwiZW1haWwiOiJhdHRhY2tlckBldmlsLmNvbSJ9.invalid_signature_hash"
    
    from fastapi.security import HTTPAuthorizationCredentials
    cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=forged_jwt)
    
    # In production, forged JWT must be rejected (raises 401)
    with pytest.raises(HTTPException) as exc_info:
        verify_scheduler_auth(settings=settings, auth_cred=cred)
    assert exc_info.value.status_code == 401

    # Operator auth must also reject forged JWT
    with pytest.raises(HTTPException) as exc_info:
        verify_operator_auth(settings=settings, auth_cred=cred)
    assert exc_info.value.status_code == 401

def test_production_safety_startup_validation():
    """Verify startup validation blocks dangerous demo configs in PRODUCTION environment."""
    with pytest.raises((ValueError, Exception)) as exc_info:
        Settings(
            app_env=AppEnvironment.PRODUCTION,
            allow_insecure_demo_auth=True,
            scheduler_api_key="prod-secret-123",
            agent_identity_secret="prod-identity-secret-123",
            admin_fallback_email="admin@company.com",
            gemini_api_key="sk-real-gemini-key",
            google_cloud_project="my-prod-project"
        )
    assert "ALLOW_INSECURE_DEMO_AUTH cannot be enabled when APP_ENV=production" in str(exc_info.value)

def test_policy_rejects_unknown_profile():
    """Verify unknown policy profiles fail closed with UNKNOWN_POLICY_PROFILE."""
    policy = PolicyEngine()
    proposal = AgentActionProposal(
        agent_id="finance-agent",
        agent_version="1.2.0",
        action_name="issue_refund",
        target_resource_id="REF-999",
        amount=Decimal("10.00"),
        currency="USD",
        recipient="user@company.com",
        justification="Test proposal"
    )
    
    decision, reason, version = policy.evaluate_proposal(proposal, profile_name="malicious-profile-v9")
    assert decision == PolicyDecisionEnum.DENY
    assert "UNKNOWN_POLICY_PROFILE" in reason
    assert version == "none"

def test_policy_rejects_unsupported_currency():
    """Verify unsupported currencies (e.g. EUR, GBP, AED) fail closed with UNSUPPORTED_CURRENCY."""
    policy = PolicyEngine()
    
    for unsupported_curr in ["EUR", "GBP", "AED"]:
        proposal = AgentActionProposal(
            agent_id="finance-agent",
            agent_version="1.2.0",
            action_name="issue_refund",
            target_resource_id="REF-CURR-1",
            amount=Decimal("20.00"),
            currency=unsupported_curr,
            recipient="user@company.com",
            justification="Testing currency rejection"
        )
        decision, reason, _ = policy.evaluate_proposal(proposal, profile_name="finance-v3")
        assert decision == PolicyDecisionEnum.DENY
        assert "UNSUPPORTED_CURRENCY" in reason

def test_policy_rejects_negative_amount():
    """Verify negative monetary amounts fail closed with INVALID_AMOUNT."""
    policy = PolicyEngine()
    proposal = AgentActionProposal(
        agent_id="finance-agent",
        agent_version="1.2.0",
        action_name="issue_refund",
        target_resource_id="REF-NEG-1",
        amount=Decimal("-100.00"),
        currency="USD",
        recipient="user@company.com",
        justification="Negative refund"
    )
    decision, reason, _ = policy.evaluate_proposal(proposal, profile_name="finance-v3")
    assert decision == PolicyDecisionEnum.DENY
    assert "INVALID_AMOUNT" in reason

def test_agent_identity_mismatch_rejection():
    """Verify identity and version binding (agent_id and agent_version mismatches)."""
    registry = AgentRegistryService()
    id_provider = AgentIdentityProvider(registry_service=registry, secret_key="secret-123")
    token = id_provider.generate_agent_token("finance-agent", "1.2.0")
    
    # 1. Agent ID mismatch in proposal
    proposal_bad_id = AgentActionProposal(
        agent_id="imposter-agent",
        agent_version="1.2.0",
        action_name="issue_refund",
        target_resource_id="REF-MISM-1",
        amount=Decimal("10.00"),
        currency="USD",
        recipient="user@company.com",
        justification="Imposter proposal"
    )
    auth_ctx = AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0", token=token)
    ok, reason, _ = id_provider.verify_agent_request(proposal_bad_id, auth_ctx)
    assert ok is False
    assert "Identity Mismatch" in reason

    # 2. Agent Version mismatch in proposal
    proposal_bad_ver = AgentActionProposal(
        agent_id="finance-agent",
        agent_version="9.9.9",
        action_name="issue_refund",
        target_resource_id="REF-MISM-2",
        amount=Decimal("10.00"),
        currency="USD",
        recipient="user@company.com",
        justification="Version mismatch proposal"
    )
    ok_v, reason_v, _ = id_provider.verify_agent_request(proposal_bad_ver, auth_ctx)
    assert ok_v is False
    assert "Version Mismatch" in reason_v

def test_concurrent_approval_single_execution():
    """Verify that concurrent approval attempts on the same pending action result in exactly ONE execution."""
    registry = AgentRegistryService()
    id_provider = AgentIdentityProvider(registry_service=registry, secret_key="secret-123")
    policy = PolicyEngine()
    memory_bank = MemoryBankService()
    worker = MockNotificationProvider()
    
    gateway = AgentGateway(
        registry=registry,
        identity_provider=id_provider,
        policy_engine=policy,
        memory_bank=memory_bank,
        worker=worker
    )

    token = id_provider.generate_agent_token("finance-agent", "1.2.0")
    proposal = AgentActionProposal(
        agent_id="finance-agent",
        agent_version="1.2.0",
        action_name="issue_refund",
        target_resource_id="REF-CONC-1",
        amount=Decimal("15000.00"),
        currency="INR",
        recipient="client@company.com",
        justification="Concurrent test refund"
    )
    auth_ctx = AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0", token=token)
    
    decision = gateway.authorize_action(proposal, auth_ctx)
    assert decision.decision == GatewayDecisionEnum.REQUIRE_HUMAN_APPROVAL
    action_id = decision.action_record_id

    # Execute 2 concurrent approvals
    results = []
    def _approve_call(op_name):
        try:
            res = gateway.approve_action(action_id, operator=op_name, notes="Concurrent test")
            return ("SUCCESS", res)
        except Exception as e:
            return ("ERROR", str(e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(_approve_call, "Operator A")
        f2 = executor.submit(_approve_call, "Operator B")
        results = [f1.result(), f2.result()]

    successes = [r for r in results if r[0] == "SUCCESS"]
    errors = [r for r in results if r[0] == "ERROR"]

    # Exactly 1 approval must succeed
    assert len(successes) == 1
    assert len(errors) == 1
    assert "already" in errors[0][1].lower()

    # Side effect notification must be sent exactly ONCE
    assert len(worker.sent_notifications) == 1

def test_human_approval_api_security():
    """Verify that approval endpoints derive operator identity from auth header, ignoring request body."""
    client = TestClient(app)
    
    # 1. Unauthenticated request to /api/gateway/actions/pending in production environment
    from approval_loop.api.routes import get_settings
    settings = get_settings()
    original_env = settings.app_env
    original_demo_auth = settings.allow_insecure_demo_auth
    
    try:
        settings.app_env = AppEnvironment.PRODUCTION
        settings.allow_insecure_demo_auth = False

        res_unauth = client.get("/api/gateway/actions/pending")
        assert res_unauth.status_code == 401

        res_app_unauth = client.post(
            "/api/gateway/actions/act_123/approve",
            json={"operator": "Attacker Pretending Admin", "notes": "Hacked"}
        )
        assert res_app_unauth.status_code == 401

        # 2. Authenticated request using valid API Key header
        headers = {"X-API-Key": settings.scheduler_api_key}
        res_auth = client.get("/api/gateway/actions/pending", headers=headers)
        assert res_auth.status_code == 200

    finally:
        settings.app_env = original_env
        settings.allow_insecure_demo_auth = original_demo_auth
