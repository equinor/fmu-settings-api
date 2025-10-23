"""Dependencies injected into FastAPI."""

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from fmu.settings._fmu_dir import UserFMUDirectory
from fmu.settings._init import init_user_fmu_directory

from fmu_settings_api.config import HttpHeader, settings
from fmu_settings_api.interfaces.smda_api import SmdaAPI
from fmu_settings_api.session import (
    ProjectSession,
    Session,
    SessionNotFoundError,
    session_manager,
)

api_token_header = APIKeyHeader(name=HttpHeader.API_TOKEN_KEY)

TokenHeaderDep = Annotated[str, Security(api_token_header)]


async def verify_auth_token(req_token: TokenHeaderDep) -> TokenHeaderDep:
    """Verifies the request token vs the stored one."""
    if req_token != settings.TOKEN:
        raise HTTPException(status_code=401, detail="Not authorized")
    return req_token


AuthTokenDep = Annotated[TokenHeaderDep, Depends(verify_auth_token)]


async def ensure_user_fmu_directory() -> UserFMUDirectory:
    """Ensures the user's FMU Directory exists.

    Returns:
        The user's UserFMUDirectory
    """
    try:
        return UserFMUDirectory()
    except FileNotFoundError:
        try:
            return init_user_fmu_directory()
        except PermissionError as e:
            raise HTTPException(
                status_code=403,
                detail="Permission denied creating user .fmu",
            ) from e
        except FileExistsError as e:
            raise HTTPException(
                status_code=409,
                detail=(
                    "User .fmu already exists but is invalid (i.e. is not a directory)"
                ),
            ) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail="Permission denied creating user .fmu",
        ) from e
    except FileExistsError as e:
        raise HTTPException(
            status_code=409,
            detail="User .fmu already exists but is invalid (i.e. is not a directory)",
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


UserFMUDirDep = Annotated[UserFMUDirectory, Depends(ensure_user_fmu_directory)]


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


async def get_smda_api(session: Session | ProjectSession) -> SmdaAPI:
    """Returns an Smda api object for the given session."""
    if session.access_tokens.smda_api is None:
        raise HTTPException(
            status_code=401,
            detail="SMDA access token is not set",
            headers={HttpHeader.UPSTREAM_SOURCE_KEY: HttpHeader.UPSTREAM_SOURCE_SMDA},
        )

    return SmdaAPI(
        access_token=session.access_tokens.smda_api.get_secret_value(),
        subscription_key=session.user_fmu_directory.get_config_value(
            "user_api_keys.smda_subscription"
        ).get_secret_value(),
    )


async def get_smda_interface(session: SessionDep) -> SmdaAPI:
    """Returns an Smda interface for the .fmu session."""
    return await get_smda_api(session)


SmdaInterfaceDep = Annotated[SmdaAPI, Depends(get_smda_interface)]


async def get_project_smda_interface(session: ProjectSmdaSessionDep) -> SmdaAPI:
    """Returns an Smda interface for the project .fmu session."""
    return await get_smda_api(session)


ProjectSmdaInterfaceDep = Annotated[SmdaAPI, Depends(get_project_smda_interface)]


async def check_write_permissions(project_session: ProjectSessionDep) -> None:
    """Check if the project allows write operations.

    Args:
        project_session: The project session containing the FMU directory.

    Raises:
        HTTPException: If the project is read-only due to lock conflicts.
    """
    fmu_dir = project_session.project_fmu_directory
    try:
        if not fmu_dir._lock.is_locked(propagate_errors=True):
            raise HTTPException(
                status_code=423,
                detail="Project is not locked. Acquire the lock before writing.",
            )
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied accessing .fmu at {fmu_dir.path}",
        ) from e
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=423,
            detail="Project lock file is missing. Project is treated as read-only.",
        ) from e
    if not fmu_dir._lock.is_acquired():
        raise HTTPException(
            status_code=423,
            detail=(
                "Project is read-only. Cannot write to project "
                "that is locked by another process."
            ),
        )


WritePermissionDep = Depends(check_write_permissions)
