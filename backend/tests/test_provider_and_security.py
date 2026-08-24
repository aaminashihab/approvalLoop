import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from approval_loop.domain.models import NotificationEnvelope, ActionType, ActionStatus
from approval_loop.worker.worker import (
    BaseNotificationProvider, MockNotificationProvider, ProductionNotificationProvider
)
from approval_loop.agent.drafter import GeminiAgentDrafter, DraftProposalResponse
from approval_loop.observability.tracer import OpenTelemetryTracer
from approval_loop.config import Settings, AppEnvironment
from approval_loop.api.auth import verify_scheduler_auth

def test_notification_provider_hierarchy():
    envelope = NotificationEnvelope(
        report_id="EXP-101",
        amount=Decimal("150.00"),
        currency="USD",
        recipient="manager@company.com",
        submitter_name="John Doe",
        subject="Action Required",
        body_text="Please sign off."
    )
    
    mock_prov = MockNotificationProvider()
    assert isinstance(mock_prov, BaseNotificationProvider)
    
    ok, receipt_id, err = mock_prov.send(envelope, "EXP-101:nudge")
    assert ok is True
    assert receipt_id is not None
    assert receipt_id.startswith("notif_")
    assert err is None
    
    # Provider deduplication
    ok_dedup, receipt_dedup, _ = mock_prov.send(envelope, "EXP-101:nudge")
    assert ok_dedup is True
    assert "notif_cached" in receipt_dedup
    
    # Fault injection
    mock_prov.simulate_failure = True
    ok_fail, receipt_fail, err_fail = mock_prov.send(envelope, "EXP-101:nudge-new")
    assert ok_fail is False
    assert receipt_fail is None
    assert "timeout" in err_fail.lower()
    
    # Production provider adapter
    prod_prov = ProductionNotificationProvider()
    assert isinstance(prod_prov, BaseNotificationProvider)
    ok_p, receipt_p, err_p = prod_prov.send(envelope, "EXP-101:prod-key")
    assert ok_p is True
    assert receipt_p.startswith("prod_notif_")

def test_drafter_structured_proposal_and_reasoning():
    drafter = GeminiAgentDrafter()
    
    # Deterministic fallback proposal
    proposal_nudge = drafter.draft_proposal(
        action_type=ActionType.NUDGE,
        report_id="EXP-202",
        submitter="Alice Smith",
        amount=Decimal("500.00"),
        currency="USD",
        description="Conference registration",
        hours_pending=28.0
    )
    assert isinstance(proposal_nudge, DraftProposalResponse)
    assert "EXP-202" in proposal_nudge.message
    assert proposal_nudge.tone == "polite_nudge"
    assert "initial follow-up" in proposal_nudge.reasoning.lower() or "pending" in proposal_nudge.reasoning.lower()
    assert proposal_nudge.references_report is True

    # Escalation proposal
    proposal_esc = drafter.draft_proposal(
        action_type=ActionType.ESCALATE,
        report_id="EXP-202",
        submitter="Alice Smith",
        amount=Decimal("500.00"),
        currency="USD",
        description="Conference registration",
        hours_pending=76.0
    )
    assert proposal_esc.tone == "urgent_escalation"
    assert "escalation" in proposal_esc.reasoning.lower()

def test_tracer_attribute_sanitization():
    tracer = OpenTelemetryTracer.get_tracer()
    tracer.start_trace("test_sanitization")
    
    with tracer.start_span("auth_check", {"api_key": "secret-12345", "token": "bearer-xyz", "report_id": "EXP-303"}):
        pass
    
    trace = tracer.end_trace()
    assert trace is not None
    span = trace.spans[0]
    assert span.attributes["api_key"] == "[REDACTED]"
    assert span.attributes["token"] == "[REDACTED]"
    assert span.attributes["report_id"] == "EXP-303"

def test_verify_scheduler_auth_header_and_oidc():
    settings = Settings(
        app_env=AppEnvironment.PRODUCTION,
        scheduler_api_key="production-secret-999",
        agent_identity_secret="prod-identity-secret-123",
        admin_fallback_email="admin@company.com",
        gemini_api_key="sk-real-gemini-key",
        google_cloud_project="my-prod-project"
    )
    
    # 1. Valid X-API-Key
    assert verify_scheduler_auth(settings=settings, x_api_key="production-secret-999") is True
    
    # 2. Invalid X-API-Key in Production raises 401
    with pytest.raises(HTTPException) as exc_info:
        verify_scheduler_auth(settings=settings, x_api_key="wrong-key")
    assert exc_info.value.status_code == 401
    
    # 3. Unverified OIDC Token (mock JWT without cryptographic signature) fails closed (raises 401)
    mock_jwt = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2FjY291bnRzLmdvb2dsZS5jb20ifQ.signature1234567890abcdef"
    cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=mock_jwt)
    with pytest.raises(HTTPException) as exc_info:
        verify_scheduler_auth(settings=settings, auth_cred=cred)
    assert exc_info.value.status_code == 401
