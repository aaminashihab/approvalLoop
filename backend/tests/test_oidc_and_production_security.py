import pytest
from approval_loop.config import Settings, AppEnvironment
from approval_loop.api.auth import _verify_oidc_jwt
from approval_loop.identity.auth_provider import AgentIdentityProvider
from approval_loop.domain.agent_registry import AgentRegistryService


def test_oidc_verification_rejects_invalid_jwt_format():
    """Task 4: OIDC token verification returns None on malformed token."""
    res = _verify_oidc_jwt("invalid.jwt.token", expected_project="my-project", expected_audience="expected-aud")
    assert res is None


def test_oidc_verification_rejects_wrong_issuer(monkeypatch):
    """Task 4: OIDC token with untrusted issuer is rejected (returns None)."""
    mock_claims = {
        "iss": "https://untrusted-issuer.attacker.com",
        "aud": "expected-aud",
        "sub": "user-123",
        "email": "user@company.com"
    }

    # Mock id_token.verify_oauth2_token
    import google.oauth2.id_token
    monkeypatch.setattr(google.oauth2.id_token, "verify_oauth2_token", lambda token, req, audience: mock_claims)

    res = _verify_oidc_jwt("mock.token.str", expected_project="my-project", expected_audience="expected-aud")
    assert res is None


def test_oidc_verification_rejects_missing_subject_claim(monkeypatch):
    """Task 4: OIDC token missing both sub and email claims is rejected (returns None)."""
    mock_claims = {
        "iss": "https://accounts.google.com",
        "aud": "expected-aud"
    }

    import google.oauth2.id_token
    monkeypatch.setattr(google.oauth2.id_token, "verify_oauth2_token", lambda token, req, audience: mock_claims)

    res = _verify_oidc_jwt("mock.token.str", expected_project="my-project", expected_audience="expected-aud")
    assert res is None


def test_gcp_oidc_auth_provider_validates_audience_and_issuer(monkeypatch):
    """Task 4: AgentIdentityProvider._verify_gcp_oidc_token validates audience and issuer."""
    registry = AgentRegistryService()
    provider = AgentIdentityProvider(registry_service=registry)

    # 1. Verification fails on invalid token
    res_bad = provider._verify_gcp_oidc_token("invalid.token", expected_agent_id="agent-1", expected_audience="aud-1")
    assert res_bad is None

    # 2. Verification fails on untrusted issuer
    mock_bad_iss = {
        "iss": "https://fake-google.com",
        "aud": "aud-1",
        "sub": "sa-123@project.iam.gserviceaccount.com"
    }
    import google.oauth2.id_token
    monkeypatch.setattr(google.oauth2.id_token, "verify_oauth2_token", lambda token, req, audience: mock_bad_iss)

    res_bad_iss = provider._verify_gcp_oidc_token("mock.token", expected_agent_id="agent-1", expected_audience="aud-1")
    assert res_bad_iss is None


def test_production_mode_fails_closed_on_dev_scheduler_key():
    """Task 5: Production environment rejects default development scheduler key."""
    with pytest.raises(ValueError, match="Default development SCHEDULER_API_KEY is prohibited in production"):
        Settings(
            app_env=AppEnvironment.PRODUCTION,
            scheduler_api_key="dev-scheduler-secret-key",
            agent_identity_secret="prod-sec-999",
            admin_fallback_email="owner@company.com",
            gemini_api_key="sk-real-gemini-key",
            google_cloud_project="prod-gcp-project"
        )


def test_production_mode_fails_closed_on_dev_identity_secret():
    """Task 5: Production environment rejects default development identity secret."""
    with pytest.raises(ValueError, match="Default AGENT_IDENTITY_SECRET is prohibited in production"):
        Settings(
            app_env=AppEnvironment.PRODUCTION,
            scheduler_api_key="prod-sched-key-123",
            agent_identity_secret="fleet-identity-master-secret-key-2026",
            admin_fallback_email="owner@company.com",
            gemini_api_key="sk-real-gemini-key",
            google_cloud_project="prod-gcp-project"
        )


def test_production_mode_fails_closed_on_insecure_demo_auth():
    """Task 5: Production environment prohibits allow_insecure_demo_auth=True."""
    with pytest.raises(ValueError, match="ALLOW_INSECURE_DEMO_AUTH cannot be enabled when APP_ENV=production"):
        Settings(
            app_env=AppEnvironment.PRODUCTION,
            allow_insecure_demo_auth=True,
            scheduler_api_key="prod-sched-key-123",
            agent_identity_secret="prod-identity-secret-123",
            admin_fallback_email="owner@company.com",
            gemini_api_key="sk-real-gemini-key",
            google_cloud_project="prod-gcp-project"
        )
