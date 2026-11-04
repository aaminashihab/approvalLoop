"""Regression tests for the security-hardening pass (auth, replay, expiry, revocation, prod gating)."""
import base64
import hashlib
import hmac
import json
import time
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from approval_loop.api.app import app
from approval_loop.api.auth import _key_matches, _verify_oidc_jwt, verify_operator_auth
from approval_loop.config import AppEnvironment, Settings
from approval_loop.domain.agent_registry import AgentRegistryService, AgentStatus
from approval_loop.domain.gateway_models import (
    AgentActionProposal, AgentAuthContext, GatewayDecisionEnum, utc_now,
)
from approval_loop.gateway.gateway import AgentGateway
from approval_loop.identity.auth_provider import AgentIdentityProvider
from approval_loop.memory.memory_bank import MemoryBankService, WorkflowState
from approval_loop.policy.policy_engine import PolicyEngine
from approval_loop.worker.worker import MockNotificationProvider

SECRET = "hardening-test-secret"


def _make_gateway(settings: Settings | None = None):
    registry = AgentRegistryService()
    ident = AgentIdentityProvider(registry_service=registry, secret_key=SECRET)
    memory = MemoryBankService()
    worker = MockNotificationProvider()
    gw = AgentGateway(registry=registry, identity_provider=ident,
                      policy_engine=PolicyEngine(settings=settings or Settings()),
                      memory_bank=memory, worker=worker)
    return gw, registry, ident, memory, worker


def _proposal(amount="20000.00", target="REF-900"):
    return AgentActionProposal(
        agent_id="finance-agent", agent_version="1.2.0", action_name="issue_refund",
        target_resource_id=target, amount=Decimal(amount), currency="INR",
        recipient="customer@company.com", justification="Duplicate charge refund",
    )


def _ctx(ident, **kw):
    return AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0",
                            token=ident.generate_agent_token("finance-agent", "1.2.0"), **kw)


def _forge_token(payload: dict) -> str:
    b64 = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode()).decode()
    return f"{b64}.{hmac.new(SECRET.encode(), b64.encode(), hashlib.sha256).hexdigest()}"


# ---------- API key handling ----------
def test_key_matches_handles_non_ascii_without_raising():
    assert _key_matches("clé-secrète", "clé-secrète") is True
    assert _key_matches("clé-secrète", "other") is False
    assert _key_matches(None, "x") is False
    assert _key_matches("x", None) is False
    assert _key_matches("", "") is False


def test_non_ascii_api_key_gets_401_not_500():
    settings = Settings(app_env=AppEnvironment.PRODUCTION, scheduler_api_key="prod-key-xyz",
                        agent_identity_secret="prod-identity-secret-123", admin_fallback_email="admin@company.com",
                        gemini_api_key="sk-real-gemini-key", google_cloud_project="my-prod-project",
                        database_url="postgresql://localhost/approvalloop_test")
    with pytest.raises(HTTPException) as exc:
        verify_operator_auth(settings=settings, x_api_key="clé-invalide")
    assert exc.value.status_code == 401


# ---------- OIDC fails closed without audience ----------
def test_operator_oidc_rejected_when_audience_not_configured():
    assert _verify_oidc_jwt("eyJ.any.token", "proj", None) is None


def test_agent_oidc_rejected_without_audience_or_binding():
    registry = AgentRegistryService()
    ident = AgentIdentityProvider(registry_service=registry, secret_key=SECRET)
    assert ident._verify_gcp_oidc_token("a.b.c", "finance-agent") is None
    ident2 = AgentIdentityProvider(registry_service=registry, secret_key=SECRET, oidc_audience="aud")
    assert ident2._verify_gcp_oidc_token("a.b.c", "finance-agent") is None  # no binding


# ---------- Token claims are mandatory ----------
def test_hmac_token_without_exp_is_rejected():
    registry = AgentRegistryService()
    ident = AgentIdentityProvider(registry_service=registry, secret_key=SECRET)
    token = _forge_token({"agent_id": "finance-agent", "agent_version": "1.2.0"})
    ok, reason, _ = ident.verify_agent_request(
        _proposal(), AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0", token=token))
    assert ok is False and "exp" in reason


def test_hmac_token_without_subject_is_rejected():
    registry = AgentRegistryService()
    ident = AgentIdentityProvider(registry_service=registry, secret_key=SECRET)
    token = _forge_token({"exp": int(time.time()) + 60})
    ok, _, _ = ident.verify_agent_request(
        _proposal(), AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0", token=token))
    assert ok is False


# ---------- Replay protection ----------
def test_replayed_request_id_is_rejected_after_success():
    registry = AgentRegistryService()
    ident = AgentIdentityProvider(registry_service=registry, secret_key=SECRET)
    ok1, _, _ = ident.verify_agent_request(_proposal(), _ctx(ident, request_id="req_fixed"))
    ok2, reason, _ = ident.verify_agent_request(_proposal(), _ctx(ident, request_id="req_fixed"))
    assert ok1 is True and ok2 is False and "Replay" in reason


def test_unauthenticated_caller_cannot_burn_request_ids():
    registry = AgentRegistryService()
    ident = AgentIdentityProvider(registry_service=registry, secret_key=SECRET)
    bad = AgentAuthContext(agent_id="finance-agent", agent_version="1.2.0",
                           token="e30=.deadbeef", request_id="req_victim")
    ok, _, _ = ident.verify_agent_request(_proposal(), bad)
    assert ok is False
    ok2, _, _ = ident.verify_agent_request(_proposal(), _ctx(ident, request_id="req_victim"))
    assert ok2 is True


def test_replay_cache_is_bounded_by_expiry():
    registry = AgentRegistryService()
    ident = AgentIdentityProvider(registry_service=registry, secret_key=SECRET)
    ident._seen_request_ids["old"] = time.time() - 1
    assert ident._consume_request_id("new") is True
    assert "old" not in ident._seen_request_ids


# ---------- Approval expiry & revocation ----------
def test_expired_approval_cannot_execute():
    gw, _, ident, memory, worker = _make_gateway(Settings(approval_ttl_seconds=60))
    prop = _proposal()
    decision = gw.authorize_action(prop, _ctx(ident))
    assert decision.decision == GatewayDecisionEnum.REQUIRE_HUMAN_APPROVAL
    wf = memory.get_workflow(prop.workflow_id)
    wf.approval_record.requested_at = utc_now() - timedelta(seconds=3600)
    memory.save_workflow(wf)

    with pytest.raises(ValueError, match="expired"):
        gw.approve_action(decision.action_record_id, operator="op")
    assert worker.sent_notifications == []
    assert memory.get_workflow(prop.workflow_id).state == WorkflowState.REJECTED


def test_approval_refused_when_agent_disabled_after_proposal():
    gw, registry, ident, memory, worker = _make_gateway()
    prop = _proposal()
    decision = gw.authorize_action(prop, _ctx(ident))
    registry.update_agent_status("finance-agent", AgentStatus.DISABLED)

    with pytest.raises(ValueError, match="no longer ACTIVE"):
        gw.approve_action(decision.action_record_id, operator="op")
    assert worker.sent_notifications == []
    # Action stays pending so an operator can still reject it.
    assert memory.get_workflow(prop.workflow_id).state == WorkflowState.PAUSED_FOR_APPROVAL
    gw.reject_action(decision.action_record_id, operator="op")


def test_failed_execution_after_approval_is_not_reported_as_success():
    gw, _, ident, memory, worker = _make_gateway()
    prop = _proposal()
    decision = gw.authorize_action(prop, _ctx(ident))
    worker.simulate_failure = True
    result = gw.approve_action(decision.action_record_id, operator="op")
    assert "FAILED" in result.reason
    wf = memory.get_workflow(prop.workflow_id)
    assert wf.state == WorkflowState.FAILED
    assert wf.metadata["pending_action"]["status"] == "approved_execution_failed"


def test_auto_execution_failure_is_surfaced_in_decision():
    gw, _, ident, memory, worker = _make_gateway()
    worker.simulate_failure = True
    prop = _proposal(amount="100.00")
    decision = gw.authorize_action(prop, _ctx(ident))
    assert decision.decision == GatewayDecisionEnum.ALLOW
    assert decision.details["execution_ok"] is False
    assert memory.get_workflow(prop.workflow_id).state == WorkflowState.FAILED


# ---------- Production gating over HTTP ----------
@pytest.fixture
def production_client():
    from approval_loop.api.routes import get_settings
    settings = get_settings()
    saved = (settings.app_env, settings.allow_insecure_demo_auth)
    settings.app_env = AppEnvironment.PRODUCTION
    settings.allow_insecure_demo_auth = False
    try:
        yield TestClient(app), settings
    finally:
        settings.app_env, settings.allow_insecure_demo_auth = saved


@pytest.mark.parametrize("method,path", [
    ("get", "/api/memory/workflows"), ("get", "/api/reports"), ("get", "/api/actions"),
    ("get", "/api/traces"), ("get", "/api/metrics"), ("get", "/api/registry/agents"),
    ("post", "/api/reports/EXP-1/resolve"),
])
def test_data_endpoints_require_auth_in_production(production_client, method, path):
    client, _ = production_client
    assert getattr(client, method)(path).status_code == 401


@pytest.mark.parametrize("path", [
    "/api/seed", "/api/demo/scenario-a", "/api/demo/scenario-b", "/api/demo/scenario-c",
    "/api/demo/reset", "/api/demo/advance-time", "/api/simulate-adversarial",
    "/api/simulate-race", "/api/simulate-notification-failure",
])
def test_demo_endpoints_do_not_exist_in_production(production_client, path):
    client, settings = production_client
    res = client.post(path, json={}, headers={"X-API-Key": settings.scheduler_api_key})
    assert res.status_code == 404


def test_cors_does_not_combine_wildcard_with_credentials():
    client = TestClient(app)
    res = client.options("/health/live", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert res.headers.get("access-control-allow-credentials") != "true"


# ---------- Policy fail-safe behavior ----------
def _policy_proposal(**kw):
    base = dict(agent_id="finance-agent", agent_version="1.2.0", action_name="issue_refund",
                target_resource_id="REF-1", recipient="customer@company.com", currency="INR")
    base.update(kw)
    return AgentActionProposal(**base)


from approval_loop.policy.policy_engine import PolicyDecisionEnum  # noqa: E402


def test_missing_amount_is_not_auto_allowed_finance():
    dec, reason, _ = PolicyEngine().evaluate_proposal(_policy_proposal(amount=None), "finance-v3")
    assert dec == PolicyDecisionEnum.REQUIRE_HUMAN_APPROVAL and "AMOUNT_MISSING" in reason


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", "sNaN", "not-a-number", True])
def test_non_finite_or_non_numeric_amount_is_rejected_by_the_model(bad):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        _policy_proposal(amount=bad)


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "not-a-number"])
def test_bad_amount_is_422_at_the_api_not_500(bad):
    body = {
        "proposal": dict(agent_id="finance-agent", agent_version="1.2.0", action_name="issue_refund",
                         target_resource_id="REF-1", recipient="customer@company.com", currency="INR", amount=bad),
        "auth_context": {"agent_id": "finance-agent", "agent_version": "1.2.0"},
    }
    assert TestClient(app).post("/api/gateway/propose", json=body).status_code == 422


def test_nan_amount_is_denied_by_policy_even_if_validation_is_bypassed():
    # Defense in depth: model_copy(update=...) skips validation, so this reaches the policy engine.
    proposal = _policy_proposal(amount=None).model_copy(update={"amount": Decimal("NaN")})
    dec, reason, _ = PolicyEngine().evaluate_proposal(proposal, "finance-v3")
    assert dec == PolicyDecisionEnum.DENY and "INVALID_AMOUNT" in reason


def test_negative_amount_still_denied():
    dec, _, _ = PolicyEngine().evaluate_proposal(_policy_proposal(amount="-5"), "finance-v3")
    assert dec == PolicyDecisionEnum.DENY


def test_sales_missing_or_garbage_discount():
    p = lambda params: _policy_proposal(agent_id="sales-agent", action_name="grant_discount", parameters=params)
    engine = PolicyEngine()
    assert engine.evaluate_proposal(p({}), "sales-v1")[0] == PolicyDecisionEnum.REQUIRE_HUMAN_APPROVAL
    assert engine.evaluate_proposal(p({"discount_percent": "abc"}), "sales-v1")[0] == PolicyDecisionEnum.DENY
    assert engine.evaluate_proposal(p({"discount_percent": "NaN"}), "sales-v1")[0] == PolicyDecisionEnum.DENY
    assert engine.evaluate_proposal(p({"discount_percent": 5}), "sales-v1")[0] == PolicyDecisionEnum.ALLOW


def test_approve_endpoint_reports_failed_execution_explicitly():
    """D8: a recorded approval whose execution failed must not look like success to API clients."""
    import approval_loop.api.routes as routes
    from approval_loop.api.app import app as _app
    client = TestClient(_app)
    key = routes.get_settings().scheduler_api_key
    proposal = routes._finance_agent_instance.propose_refund("REF-D8", "c@client.com", Decimal("20000.00"))
    routes.get_gateway().authorize_action(*proposal)
    action_id = next(p["action_id"] for p in routes.get_gateway().list_pending_actions()
                     if p["proposal"]["target_resource_id"] == "REF-D8")
    worker = routes.get_gateway().worker
    worker.simulate_failure = True
    try:
        res = client.post(f"/api/gateway/actions/{action_id}/approve", json={"notes": ""}, headers={"X-API-Key": key})
    finally:
        worker.simulate_failure = False
    body = res.json()
    assert res.status_code == 200
    assert body["execution"]["executed"] is False and body["execution"]["error"]
    assert "failed" in body["message"]
