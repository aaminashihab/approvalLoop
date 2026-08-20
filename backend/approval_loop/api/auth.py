import os
from fastapi import Header, HTTPException, Security, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from approval_loop.config import AppEnvironment, Settings

security_bearer = HTTPBearer(auto_error=False)

def get_settings_dep():
    from approval_loop.api.routes import get_settings
    return get_settings()

def verify_scheduler_auth(
    settings: Settings = Depends(get_settings_dep),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    auth_cred: HTTPAuthorizationCredentials | None = Security(security_bearer)
) -> bool:
    expected_key = settings.scheduler_api_key

    # Check X-API-Key header
    if x_api_key and x_api_key == expected_key:
        return True

    # Check Bearer token (OIDC / Bearer)
    if auth_cred and auth_cred.credentials == expected_key:
        return True

    # In TEST/DEMO mode with default development key, allow unauthenticated local dev if explicitly configured
    if settings.app_env in (AppEnvironment.TEST, AppEnvironment.DEMO):
        if not x_api_key and not auth_cred:
            return True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: invalid or missing Cloud Scheduler authentication credentials."
    )
