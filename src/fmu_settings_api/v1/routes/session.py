"""The main router for /api/v1/session."""

import contextlib
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fmu.settings import find_nearest_fmu_directory

from fmu_settings_api.config import settings
from fmu_settings_api.deps import (
    AuthTokenDep,
    SessionDep,
    UserFMUDirDep,
    get_session,
    verify_auth_token,
)
from fmu_settings_api.models import AccessToken, FMUProject, Message, SessionResponse
from fmu_settings_api.session import (
    add_access_token_to_session,
    add_fmu_project_to_session,
    create_fmu_session,
    destroy_fmu_session,
)
from fmu_settings_api.v1.responses import CreateSessionResponses, GetSessionResponses

router = APIRouter(prefix="/session", tags=["session"])


@router.post(
    "/",
    response_model=SessionResponse,
    dependencies=[Depends(verify_auth_token)],
    summary="Creates a session for the user",
    description=(
        "When creating a session the application will ensure that the user "
        ".fmu directory exists by creating it if it does not. It will also "
        "check for the nearest project .fmu directory above the current "
        "working directory, and if one exists, add it to the session. If "
        "it does not exist its value will be `null`.\n"
        "If a session already exists when POSTing to this route, the existing "
        "session will be silently destroyed. This will remove any state for "
        "a project .fmu that may be opened.\n"
        "The session cookie set by this route is required for all other "
        "routes. Sessions are not persisted when the API is shut down."
    ),
    responses=CreateSessionResponses,
)
async def create_session(
    response: Response,
    auth_token: AuthTokenDep,
    user_fmu_dir: UserFMUDirDep,
    fmu_settings_session: Annotated[str | None, Cookie()] = None,
) -> SessionResponse:
    """Establishes a user session."""
    if fmu_settings_session:
        await destroy_fmu_session(fmu_settings_session)

    try:
        session_id = await create_fmu_session(user_fmu_dir)
        response.set_cookie(
            key=settings.SESSION_COOKIE_KEY,
            value=session_id,
            httponly=True,
            secure=False,
            samesite="lax",
        )
        obfuscated_user_config = user_fmu_dir.config.load().obfuscate_secrets()

        session_response = SessionResponse(user_config=obfuscated_user_config)

        with contextlib.suppress(FileNotFoundError):
            path = Path.cwd()
            project_fmu_dir = find_nearest_fmu_directory(path)
            _ = await add_fmu_project_to_session(session_id, project_fmu_dir)
            session_response.fmu_project = FMUProject(
                path=project_fmu_dir.base_path,
                project_dir_name=project_fmu_dir.base_path.name,
                config=project_fmu_dir.config.load(),
            )

        return session_response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch(
    "/access_token",
    response_model=Message,
    dependencies=[Depends(get_session)],
    summary="Adds a known access token to the session",
    description=(
        "This route should be used to add a scoped access token to the current "
        "session. The token applied via this route is typically a depndency for "
        "other routes."
    ),
    responses={
        **GetSessionResponses,
        400: {
            "description": (
                "Occurs when trying to save a key to an unknown access scope. An "
                "access scope/token is unknown if it is not a predefined field in the "
                "the session manager's 'AccessTokens' model."
            ),
            "content": {
                "application/json": {
                    "example": {
                        "examples": [
                            {
                                "detail": (
                                    "Access token id {acess_token.id} is not known or "
                                    "supported"
                                ),
                            },
                        ],
                    },
                },
            },
        },
    },
)
async def patch_access_token(session: SessionDep, access_token: AccessToken) -> Message:
    """Patches a known SSO access token into the session."""
    try:
        await add_access_token_to_session(session.id, access_token)
        return Message(message=f"Set session access token for {access_token.id}")
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Access token id {access_token.id} is not known or supported",
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
