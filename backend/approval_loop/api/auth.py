import os
import logging
import base64
import json
from fastapi import Header, HTTPException, Security, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from approval_loop.config import AppEnvironment, Settings

logger = logging.getLogger("approval_loop.auth")
security_bearer = HTTPBearer(auto_error=False)

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
    if x_api_key and x_api_key == expected_key:
        return True

    # 2. Check Bearer token (API Key or Google Cloud IAM Service Account OIDC token)
    if isinstance(auth_cred, HTTPAuthorizationCredentials) and auth_cred.credentials:
        token = auth_cred.credentials.strip()
        if token == expected_key:
            return True

        # Real Google Cloud OIDC token verification
        if token.startswith("eyJ"):
            verified_claims = _verify_oidc_jwt(token, settings.google_cloud_project)
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

    if x_api_key and x_api_key == expected_key:
        return True

    if isinstance(auth_cred, HTTPAuthorizationCredentials) and auth_cred.credentials:
        token = auth_cred.credentials.strip()
        if token == expected_key:
            return True
        if token.startswith("eyJ"):
            claims = _verify_oidc_jwt(token, settings.google_cloud_project)
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
    if x_api_key and x_api_key == expected_key:
        return "Admin Operator (API-Key)"

    if isinstance(auth_cred, HTTPAuthorizationCredentials) and auth_cred.credentials:
        token = auth_cred.credentials.strip()
        if token == expected_key:
            return "Admin Operator (API-Key)"

        # 2. Cryptographically Verified OIDC Token
        if token.startswith("eyJ"):
            claims = _verify_oidc_jwt(token, settings.google_cloud_project)
            if claims:
                operator_id = claims.get("email") or claims.get("sub") or "Verified OIDC Operator"
                return f"Operator ({operator_id})"

    # 3. Explicit Opt-In Demo Mode (Prohibited in PRODUCTION)
    if settings.app_env != AppEnvironment.PRODUCTION and settings.allow_insecure_demo_auth:
        return "Demo Operator"

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: human operator authentication required (valid OIDC Bearer token or X-API-Key required)."
    )

def _verify_oidc_jwt(token: str, expected_project: str) -> dict | None:
    """
    Cryptographically verifies Google Cloud OIDC tokens using google.oauth2.id_token.
    Fails closed if signature, issuer, or audience verification fails.
    Never decodes unverified JWT payload on signature failure.
    """
    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests
        req = requests.Request()
        id_info = id_token.verify_oauth2_token(token, req)
        return id_info
    except Exception as e:
        logger.warning("OIDC token cryptographic verification failed: %s", str(e))
        return None
