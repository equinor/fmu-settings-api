"""Session dependencies."""

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException

from fmu_settings_api.config import HttpHeader
from fmu_settings_api.services.session import SessionService
from fmu_settings_api.session import (
    ProjectSession,
    Session,
    SessionNotFoundError,
    destroy_fmu_session_if_expired,
    get_fmu_session,
)


async def destroy_session_if_expired(
    fmu_settings_session: Annotated[str | None, Cookie()] = None,
) -> None:
    """Destroys a session from the session manager if it has expired."""
    return (
        await destroy_fmu_session_if_expired(fmu_settings_session)
        if fmu_settings_session
        else None
    )


DestroySessionIfExpiredDep = Annotated[None, Depends(destroy_session_if_expired)]


async def get_session(
    expired_session_dep: DestroySessionIfExpiredDep,
    fmu_settings_session: Annotated[str | None, Cookie()] = None,
) -> Session:
    """Gets an active session from the session manager."""
    if not fmu_settings_session:
        raise HTTPException(
            status_code=401,
            detail="No active session found",
            headers={
                HttpHeader.WWW_AUTHENTICATE_KEY: HttpHeader.WWW_AUTHENTICATE_COOKIE
            },
        )
    try:
        return await get_fmu_session(fmu_settings_session)
    except SessionNotFoundError as e:
        raise HTTPException(
            status_code=401,
            detail="No active session found",
            headers={
                HttpHeader.WWW_AUTHENTICATE_KEY: HttpHeader.WWW_AUTHENTICATE_COOKIE
            },
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Session error: {e}") from e


SessionDep = Annotated[Session, Depends(get_session)]


async def get_project_session(session: SessionDep) -> ProjectSession:
    """Gets a session with an FMU Project opened from the session manager."""
    if not isinstance(session, ProjectSession):
        raise HTTPException(
            status_code=401,
            detail="No FMU project directory open",
        )

    if not session.project_fmu_directory.path.exists():
        raise HTTPException(
            status_code=404,
            detail="Project .fmu directory not found. It may have been deleted.",
        )
    return session


ProjectSessionDep = Annotated[ProjectSession, Depends(get_project_session)]


async def ensure_smda_session(session: Session) -> None:
    """Raises exceptions if a session is not SMDA-query capable."""
    if (
        session.user_fmu_directory.get_config_value("user_api_keys.smda_subscription")
        is None
    ):
        raise HTTPException(
            status_code=401,
            detail="User SMDA API key is not configured",
            headers={HttpHeader.UPSTREAM_SOURCE_KEY: HttpHeader.UPSTREAM_SOURCE_SMDA},
        )
    if session.access_tokens.smda_api is None:
        raise HTTPException(
            status_code=401,
            detail="SMDA access token is not set",
            headers={HttpHeader.UPSTREAM_SOURCE_KEY: HttpHeader.UPSTREAM_SOURCE_SMDA},
        )


async def get_smda_session(session: SessionDep) -> Session:
    """Gets a session capable of querying SMDA from the session manager."""
    await ensure_smda_session(session)
    return session


async def get_project_smda_session(session: ProjectSessionDep) -> ProjectSession:
    """Returns a project .fmu session that is SMDA-querying capable."""
    await ensure_smda_session(session)
    return session


ProjectSmdaSessionDep = Annotated[ProjectSession, Depends(get_project_smda_session)]


async def get_session_service(
    session: SessionDep,
) -> SessionService:
    """Returns a SessionService instance for the session."""
    return SessionService(session)


SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]


async def get_project_session_service(
    session: ProjectSessionDep,
) -> SessionService:
    """Returns a SessionService instance for a project session."""
    return SessionService(session)


ProjectSessionServiceDep = Annotated[
    SessionService, Depends(get_project_session_service)
]
