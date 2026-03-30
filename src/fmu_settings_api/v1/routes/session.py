"""The main router for /api/v1/session."""

import contextlib
from pathlib import Path
from textwrap import dedent
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Response
from fmu.settings import find_nearest_fmu_directory
from fmu.settings._resources.lock_manager import LockError

from fmu_settings_api.config import settings
from fmu_settings_api.deps import (
    AuthTokenDep,
    SessionServiceDep,
    UserFMUDirDep,
)
from fmu_settings_api.deps.session import DestroySessionIfExpiredDep
from fmu_settings_api.models import AccessToken, Message, SessionResponse
from fmu_settings_api.session import (
    SessionNotFoundError,
    add_fmu_project_to_session,
    create_fmu_session,
    get_fmu_session,
    get_rms_session_expiration,
    renew_fmu_session,
)
from fmu_settings_api.v1.responses import (
    CreateSessionResponses,
    GetSessionResponses,
    inline_add_response,
)

router = APIRouter(prefix="/session", tags=["session"])

SessionRestoreResponses = {
    **inline_add_response(
        403,
        "Permission denied while restoring a .fmu directory",
        [{"detail": "Permission denied recovering .fmu resources"}],
    ),
    **inline_add_response(
        409,
        "A .fmu path exists but is not a directory",
        [{"detail": ".fmu exists at {path} but is not a directory"}],
    ),
    **inline_add_response(
        423,
        "Project is locked by another process and cannot be restored",
        [{"detail": "Project lock conflict: {error_message}"}],
    ),
}


@router.post(
    "/",
    response_model=SessionResponse,
    summary="Creates a new user session.",
    description=dedent(
        """
        When creating a session the application will ensure that the user
        .fmu directory exists by creating it if it does not.

        If a valid session already exists when POSTing to this route, the
        existing session will be renewed with a new expiry date and a new
        session cookie value.

        After creating the session, the application will attempt to find the
        nearest project .fmu directory above the current working directory and
        add it to the session if found. If not found, no project will be
        associated. Renewing an existing session keeps its current state.

        The session cookie set by this route is required for all other
        routes. Sessions are not persisted when the API is shut down.
        """
    ),
    responses=CreateSessionResponses,
)
async def post_session(
    response: Response,
    auth_token: AuthTokenDep,
    user_fmu_dir: UserFMUDirDep,
    expired_session_dep: DestroySessionIfExpiredDep,
    fmu_settings_session: Annotated[str | None, Cookie()] = None,
) -> SessionResponse:
    """Creates a new user session."""
    if fmu_settings_session:
        try:
            session = await renew_fmu_session(fmu_settings_session)
            response.set_cookie(
                key=settings.SESSION_COOKIE_KEY,
                value=session.id,
                httponly=True,
                secure=False,
                samesite="lax",
            )
            return SessionResponse(
                id=session.id,
                created_at=session.created_at,
                expires_at=session.expires_at,
                rms_expires_at=await get_rms_session_expiration(session.id),
                last_accessed=session.last_accessed,
            )
        except SessionNotFoundError:
            pass

    session_id = await create_fmu_session(user_fmu_dir)

    response.set_cookie(
        key=settings.SESSION_COOKIE_KEY,
        value=session_id,
        httponly=True,
        secure=False,
        samesite="lax",
    )

    with contextlib.suppress(FileNotFoundError, LockError):
        path = Path.cwd()
        project_fmu_dir = find_nearest_fmu_directory(path)
        await add_fmu_project_to_session(session_id, project_fmu_dir)

    session = await get_fmu_session(session_id)

    return SessionResponse(
        id=session.id,
        created_at=session.created_at,
        expires_at=session.expires_at,
        rms_expires_at=None,
        last_accessed=session.last_accessed,
    )


@router.patch(
    "/access_token",
    response_model=Message,
    summary="Adds a known access token to the session",
    description=dedent(
        """
        This route should be used to add a scoped access token to the current
        session. The token applied via this route is typically a dependency for
        other routes.
        """
    ),
    responses={
        **GetSessionResponses,
        **inline_add_response(
            400,
            dedent(
                """
                Occurs when trying to save a key to an unknown access scope. An
                access scope/token is unknown if it is not a predefined field in the
                the session manager's 'AccessTokens' model.
                """
            ),
            [
                {
                    "detail": (
                        "Access token id {access_token.id} is not known or supported"
                    ),
                },
            ],
        ),
    },
)
async def patch_access_token(
    session_service: SessionServiceDep, access_token: AccessToken
) -> Message:
    """Patches a known SSO access token into the session."""
    try:
        access_token_id = await session_service.add_access_token(access_token)
        return Message(message=f"Set session access token for {access_token_id}")
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Access token id {access_token.id} is not known or supported",
        ) from e


@router.get(
    "/",
    response_model=SessionResponse,
    summary="Fetches the current session state",
    description=dedent(
        """
        Retrieves the latest session metadata.
        """
    ),
    responses=GetSessionResponses,
)
async def get_session(
    session_service: SessionServiceDep,
) -> SessionResponse:
    """Returns the current session in a serialisable format."""
    return await session_service.get_session_response()


@router.post(
    "/restore",
    response_model=Message,
    summary="Restores missing .fmu resources for the current session",
    description=dedent(
        """
        Attempts to recover missing .fmu content from in-memory state.

        For all sessions this restores the user .fmu directory. If a project is
        attached to the session, the project .fmu directory is restored as well.
        """
    ),
    responses={**GetSessionResponses, **SessionRestoreResponses},
)
async def post_restore(session_service: SessionServiceDep) -> Message:
    """Attempt recovery of missing .fmu directories."""
    try:
        session_service.restore_fmu_directories()
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except PermissionError as e:
        if "Cannot write to .fmu directory because it is locked by" in str(e):
            raise HTTPException(
                status_code=423,
                detail=f"Project lock conflict: {e}",
            ) from e
        raise HTTPException(
            status_code=403,
            detail="Permission denied recovering .fmu resources",
        ) from e

    return Message(message="Restored .fmu resources")
