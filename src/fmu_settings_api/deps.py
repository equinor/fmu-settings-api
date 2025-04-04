"""Dependencies injected into FastAPI."""

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from fmu_settings_api.config import settings
from fmu_settings_api.session import Session, session_manager

api_token_header = APIKeyHeader(name=settings.TOKEN_HEADER_NAME)

TokenHeaderDep = Annotated[str, Security(api_token_header)]


async def verify_auth_token(req_token: TokenHeaderDep) -> TokenHeaderDep:
    """Verifies the request token vs the stored one."""
    if req_token != settings.TOKEN:
        raise HTTPException(status_code=401, detail="Not authorized")
    return req_token


async def get_fmu_session(fmu_settings_session: str | None = Cookie(None)) -> Session:
    """Gets a session from the session manager."""
    if not fmu_settings_session:
        raise HTTPException(
            status_code=401,
            detail="No active session found",
            headers={"WWW-Authenticate": "Cookie-Auth"},
        )
    try:
        session = await session_manager.get_session(fmu_settings_session)
        if not session:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired session",
                headers={"WWW-Authenticate": "Cookie-Auth"},
            )
        return session
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"Session error: {e}") from e


SessionDep = Annotated[Session, Depends(get_fmu_session)]
