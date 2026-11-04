import os
import hmac
import logging
import base64
import json
from fastapi import Header, HTTPException, Security, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from approval_loop.config import AppEnvironment, Settings

logger = logging.getLogger("approval_loop.auth")
security_bearer = HTTPBearer(auto_error=False)

def _key_matches(candidate: object, expected: object) -> bool:
    """Constant-time API key comparison (UTF-8 bytes, so non-ASCII input cannot raise).

    Anything that is not a non-empty string never matches. This also covers FastAPI's Header()
    default object, which is what arrives when the dependency is called directly.
    """
    if not isinstance(candidate, str) or not isinstance(expected, str) or not candidate or not expected:
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))

def get_settings_dep():
    from approval_loop.api.routes import get_settings
    return get_settings()

def verify_scheduler_auth(
    settings: Settings = Depends(get_settings_dep),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    auth_cred: HTTPAuthorizationCredentials | None = Security(security_bearer)
) -> bool:
    """
    Verifies Cloud Scheduler ingress authorization:
    Supports:
    1. Header 'X-API-Key: <key>'
    2. Header 'Authorization: Bearer <key_or_token>' with Google Cloud IAM verification
    3. Explicit opt-in demo unauthenticated fallback for development/test only.
    """
    expected_key = settings.scheduler_api_key

    # 1. Check X-API-Key header
    if _key_matches(x_api_key, expected_key):
        return True

    # 2. Check Bearer token (API Key or Google Cloud IAM Service Account OIDC token)
    if isinstance(auth_cred, HTTPAuthorizationCredentials) and auth_cred.credentials:
        token = auth_cred.credentials.strip()
        if _key_matches(token, expected_key):
            return True

        # Real Google Cloud OIDC token verification
        if token.startswith("eyJ"):
            verified_claims = _verify_oidc_jwt(token, settings.google_cloud_project, settings.oidc_audience)
            if verified_claims:
                logger.info("Authenticated Cloud Scheduler trigger via verified OIDC token (sub: %s)", verified_claims.get("sub"))
                return True

    # 3. In TEST and DEMO modes, allow unauthenticated requests ONLY if ALLOW_INSECURE_DEMO_AUTH is enabled
    if settings.app_env != AppEnvironment.PRODUCTION and settings.allow_insecure_demo_auth:
        if not x_api_key and not isinstance(auth_cred, HTTPAuthorizationCredentials):
            return True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: invalid or missing Cloud Scheduler authentication credentials (X-API-Key or valid OIDC Bearer token required)."
    )

def verify_admin_auth(
    settings: Settings = Depends(get_settings_dep),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    auth_cred: HTTPAuthorizationCredentials | None = Security(security_bearer)
) -> bool:
    """
    Verifies administrative authorization for sensitive registry and policy mutations.
    """
    expected_key = settings.scheduler_api_key

    if _key_matches(x_api_key, expected_key):
        return True

    if isinstance(auth_cred, HTTPAuthorizationCredentials) and auth_cred.credentials:
        token = auth_cred.credentials.strip()
        if _key_matches(token, expected_key):
            return True
        if token.startswith("eyJ"):
            claims = _verify_oidc_jwt(token, settings.google_cloud_project, settings.oidc_audience)
            if claims:
                return True

    if settings.app_env != AppEnvironment.PRODUCTION and settings.allow_insecure_demo_auth:
        return True

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden: Administrative privileges required for registry modification."
    )

def verify_operator_auth(
    settings: Settings = Depends(get_settings_dep),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    auth_cred: HTTPAuthorizationCredentials | None = Security(security_bearer)
) -> str:
    """
    Verifies human operator authorization for pending approvals and human-in-the-loop sign-offs.
    Returns the verified operator principal identity string.
    Identities are derived ONLY from cryptographically verified auth credentials.
    Client-supplied request body strings (e.g. {"operator": "..."}) MUST NOT be trusted for identity.
    """
    expected_key = settings.scheduler_api_key

    # 1. API Key Authorization
    if _key_matches(x_api_key, expected_key):
        return "Admin Operator (API-Key)"

    if isinstance(auth_cred, HTTPAuthorizationCredentials) and auth_cred.credentials:
        token = auth_cred.credentials.strip()
        if _key_matches(token, expected_key):
            return "Admin Operator (API-Key)"

        # 2. Cryptographically Verified OIDC Token
        if token.startswith("eyJ"):
            claims = _verify_oidc_jwt(token, settings.google_cloud_project, settings.oidc_audience)
            if claims:
                verified_email = claims.get("email") if claims.get("email_verified") else None
                operator_id = verified_email or claims.get("sub") or "Verified OIDC Operator"
                return f"Operator ({operator_id})"

    # 3. Explicit Opt-In Demo Mode (Prohibited in PRODUCTION)
    if settings.app_env != AppEnvironment.PRODUCTION and settings.allow_insecure_demo_auth:
        return "Demo Operator"

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: human operator authentication required (valid OIDC Bearer token or X-API-Key required)."
    )

def _verify_oidc_jwt(token: str, expected_project: str, expected_audience: str | None = None) -> dict | None:
    """
    Cryptographically verifies Google OIDC tokens using google.oauth2.id_token.

    Fails closed when:
    - no expected audience is configured (OIDC_AUDIENCE): without an audience check, ANY
      Google-signed ID token (e.g. for any Google account) would authenticate;
    - signature, expiry or audience verification fails;
    - the issuer is not Google, or the token has neither a subject nor an email claim.
    """
    audience = expected_audience
    if not audience:
        logger.warning("OIDC bearer token rejected: OIDC_AUDIENCE is not configured (OIDC auth disabled).")
        return None
    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests
        req = requests.Request()
        id_info = id_token.verify_oauth2_token(token, req, audience=audience)
        iss = id_info.get("iss", "")
        if iss not in ("https://accounts.google.com", "accounts.google.com"):
            logger.warning("OIDC token verification failed: untrusted issuer %s", iss)
            return None
        if not id_info.get("sub") and not id_info.get("email"):
            logger.warning("OIDC token verification failed: missing subject/email claim")
            return None
        return id_info
    except Exception as e:
        logger.warning("OIDC token cryptographic verification failed: %s", type(e).__name__)
        return None


def require_operator_in_production(
    settings: Settings = Depends(get_settings_dep),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    auth_cred: HTTPAuthorizationCredentials | None = Security(security_bearer)
) -> str:
    """Operator auth is enforced in PRODUCTION; non-production keeps the open demo behavior."""
    if settings.app_env == AppEnvironment.PRODUCTION:
        return verify_operator_auth(settings=settings, x_api_key=x_api_key, auth_cred=auth_cred)
    return "non-production"
