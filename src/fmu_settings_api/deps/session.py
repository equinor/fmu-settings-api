"""Session dependencies."""

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException

from fmu_settings_api.config import HttpHeader
from fmu_settings_api.services.session import SessionService
from fmu_settings_api.session import (
    ProjectSession,
    Session,
    SessionNotFoundError,
    session_manager,
)


async def get_session(
    fmu_settings_session: Annotated[str | None, Cookie()] = None,
) -> Session:
    """Gets a session from the session manager."""
    if not fmu_settings_session:
        raise HTTPException(
            status_code=401,
            detail="No active session found",
            headers={
                HttpHeader.WWW_AUTHENTICATE_KEY: HttpHeader.WWW_AUTHENTICATE_COOKIE
            },
        )
    try:
        return await session_manager.get_session(fmu_settings_session)
    except SessionNotFoundError as e:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session",
            headers={
                HttpHeader.WWW_AUTHENTICATE_KEY: HttpHeader.WWW_AUTHENTICATE_COOKIE
            },
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Session error: {e}") from e


SessionDep = Annotated[Session, Depends(get_session)]


async def get_session_no_extend(
    fmu_settings_session: Annotated[str | None, Cookie()] = None,
) -> Session:
    """Gets a session from the session manager without extending expiration."""
    if not fmu_settings_session:
        raise HTTPException(
            status_code=401,
            detail="No active session found",
            headers={
                HttpHeader.WWW_AUTHENTICATE_KEY: HttpHeader.WWW_AUTHENTICATE_COOKIE
            },
        )
    try:
        return await session_manager.get_session(
            fmu_settings_session, extend_expiration=False
        )
    except SessionNotFoundError as e:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session",
            headers={
                HttpHeader.WWW_AUTHENTICATE_KEY: HttpHeader.WWW_AUTHENTICATE_COOKIE
            },
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Session error: {e}") from e


SessionNoExtendDep = Annotated[Session, Depends(get_session_no_extend)]


async def get_project_session(
    fmu_settings_session: str | None = Cookie(None),
) -> ProjectSession:
    """Gets a session with an FMU Project opened from the session manager."""
    session = await get_session(fmu_settings_session)
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


async def get_project_session_no_extend(
    fmu_settings_session: str | None = Cookie(None),
) -> ProjectSession:
    """Gets a session with an FMU Project opened from the session manager."""
    session = await get_session_no_extend(fmu_settings_session)
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


ProjectSessionNoExtendDep = Annotated[
    ProjectSession, Depends(get_project_session_no_extend)
]


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


async def get_smda_session(
    fmu_settings_session: str | None = Cookie(None),
) -> Session:
    """Gets a session capable of querying SMDA from the session manager."""
    session = await get_session(fmu_settings_session)
    await ensure_smda_session(session)
    return session


async def get_project_smda_session(
    fmu_settings_session: str | None = Cookie(None),
) -> ProjectSession:
    """Returns a project .fmu session that is SMDA-querying capable."""
    session = await get_project_session(fmu_settings_session)
    await ensure_smda_session(session)
    return session


ProjectSmdaSessionDep = Annotated[ProjectSession, Depends(get_project_smda_session)]


async def get_session_service(
    session: SessionDep,
) -> SessionService:
    """Returns a SessionService instance for the session."""
    return SessionService(session)


async def get_session_service_no_extend(
    session: SessionNoExtendDep,
) -> SessionService:
    """Returns a SessionService instance without extending session expiration."""
    return SessionService(session)


SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
SessionServiceNoExtendDep = Annotated[
    SessionService, Depends(get_session_service_no_extend)
]


async def get_project_session_service(
    session: ProjectSessionDep,
) -> SessionService:
    """Returns a SessionService instance for a project session."""
    return SessionService(session)


async def get_project_session_service_no_extend(
    session: ProjectSessionNoExtendDep,
) -> SessionService:
    """Returns a SessionService for a project session without extending expiration."""
    return SessionService(session)


ProjectSessionServiceDep = Annotated[
    SessionService, Depends(get_project_session_service)
]
ProjectSessionServiceNoExtendDep = Annotated[
    SessionService, Depends(get_project_session_service_no_extend)
]
