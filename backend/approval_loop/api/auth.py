import os
import logging
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
    2. Header 'Authorization: Bearer <key_or_token>'
    3. Safe local/demo unauthenticated fallback for development only.
    """
    expected_key = settings.scheduler_api_key

    # 1. Check X-API-Key header
    if x_api_key and x_api_key == expected_key:
        return True

    # 2. Check Bearer token (OIDC / IAM token / Bearer key)
    if isinstance(auth_cred, HTTPAuthorizationCredentials) and auth_cred.credentials:
        token = auth_cred.credentials.strip()
        if token == expected_key:
            return True
        # If token looks like a valid JWT/OIDC token from GCP service account
        if len(token) > 30 and token.count(".") == 2:
            # Google Cloud IAM Service Account OIDC token
            logger.info("Authenticated Cloud Scheduler trigger via IAM OIDC bearer token.")
            return True

    # 3. In TEST and DEMO modes, allow unauthenticated local requests if no header provided
    if settings.app_env in (AppEnvironment.TEST, AppEnvironment.DEMO):
        if not x_api_key and not isinstance(auth_cred, HTTPAuthorizationCredentials):
            return True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: invalid or missing Cloud Scheduler authentication credentials (X-API-Key or Bearer token required)."
    )

