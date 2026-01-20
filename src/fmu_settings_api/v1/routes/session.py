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
    SessionServiceNoExtendDep,
    UserFMUDirDep,
)
from fmu_settings_api.models import AccessToken, Message, SessionResponse
from fmu_settings_api.session import (
    ProjectSession,
    add_fmu_project_to_session,
    add_rms_project_to_session,
    create_fmu_session,
    destroy_fmu_session,
    remove_rms_project_from_session,
    session_manager,
)
from fmu_settings_api.v1.responses import (
    CreateSessionResponses,
    GetSessionResponses,
    inline_add_response,
)

router = APIRouter(prefix="/session", tags=["session"])


@router.post(
    "/",
    response_model=SessionResponse,
    summary="Creates a session for the user",
    description=dedent(
        """
        When creating a session the application will ensure that the user
        .fmu directory exists by creating it if it does not.

        If a session already exists when POSTing to this route, the new session
        will preserve the access tokens from the old session. If the old session
        had a project .fmu directory, it will also be added to the new session.
        After migrating the state, the old session is destroyed.

        If no previous session exists, the application will attempt to find the
        nearest project .fmu directory above the current working directory and
        add it to the session if found. If not found, no project will be associated.

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
    fmu_settings_session: Annotated[str | None, Cookie()] = None,
) -> SessionResponse:
    """Establishes a user session."""
    old_session = None
    if fmu_settings_session:
        with contextlib.suppress(Exception):
            old_session = await session_manager.get_session(
                fmu_settings_session, extend_expiration=False
            )

    session_id = await create_fmu_session(user_fmu_dir)
    response.set_cookie(
        key=settings.SESSION_COOKIE_KEY,
        value=session_id,
        httponly=True,
        secure=False,
        samesite="lax",
    )

    if old_session and fmu_settings_session:
        new_session = await session_manager.get_session(session_id)
        new_session.access_tokens = old_session.access_tokens

        if isinstance(old_session, ProjectSession):
            await add_fmu_project_to_session(
                session_id, old_session.project_fmu_directory
            )

            rms_session = old_session.rms_session
            if rms_session is not None:
                # Transfer existing RMS session to new session
                await add_rms_project_to_session(
                    session_id,
                    rms_session.root,
                    rms_session.project,
                )
                await remove_rms_project_from_session(
                    fmu_settings_session, cleanup=False
                )

        await destroy_fmu_session(fmu_settings_session)
    else:
        with contextlib.suppress(FileNotFoundError, LockError):
            path = Path.cwd()
            project_fmu_dir = find_nearest_fmu_directory(path)
            await add_fmu_project_to_session(session_id, project_fmu_dir)

    session = await session_manager.get_session(session_id)
    return SessionResponse(
        id=session.id,
        created_at=session.created_at,
        expires_at=session.expires_at,
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
    session_service: SessionServiceNoExtendDep,
) -> SessionResponse:
    """Returns the current session in a serialisable format."""
    return session_service.get_session_response()
