"""Dependencies injected into FastAPI."""

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from fmu.settings._fmu_dir import UserFMUDirectory
from fmu.settings._init import init_user_fmu_directory

from fmu_settings_api.config import settings
from fmu_settings_api.session import (
    ProjectSession,
    Session,
    SessionNotFoundError,
    session_manager,
)

api_token_header = APIKeyHeader(name=settings.TOKEN_HEADER_NAME)

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
            headers={"WWW-Authenticate": "Cookie-Auth"},
        )
    try:
        return await session_manager.get_session(fmu_settings_session)
    except SessionNotFoundError as e:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Cookie-Auth"},
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
            headers={"x-upstream-source": "SMDA"},
        )
    if session.access_tokens.smda_api is None:
        raise HTTPException(
            status_code=401,
            detail="SMDA access token is not set",
            headers={"x-upstream-source": "SMDA"},
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
