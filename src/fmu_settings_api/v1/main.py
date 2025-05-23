"""The main router for /api/v1."""

import contextlib
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fmu.settings import find_nearest_fmu_directory

from fmu_settings_api.config import settings
from fmu_settings_api.deps import (
    AuthTokenDep,
    UserFMUDirDep,
    get_session,
    verify_auth_token,
)
from fmu_settings_api.models import FMUProject, HealthCheck, SessionResponse
from fmu_settings_api.session import (
    add_fmu_project_to_session,
    create_fmu_session,
)
from fmu_settings_api.v1.responses import GetSessionResponses

from .routes import project, user

api_v1_router = APIRouter(prefix=settings.API_V1_PREFIX, tags=["v1"])

api_v1_router.include_router(project.router, dependencies=[Depends(get_session)])
api_v1_router.include_router(user.router, dependencies=[Depends(get_session)])


@api_v1_router.get(
    "/health",
    response_model=HealthCheck,
    dependencies=[Depends(get_session)],
    summary="A health check on the /v1 routes.",
    description=(
        "This route requires a valid session to return 200 OK. it can used to "
        "check if the user has a valid session."
    ),
    responses=GetSessionResponses,
)
async def v1_health_check() -> HealthCheck:
    """Simple health check endpoint."""
    return HealthCheck()


@api_v1_router.post(
    "/session",
    response_model=SessionResponse,
    dependencies=[Depends(verify_auth_token)],
)
async def create_session(
    response: Response,
    auth_token: AuthTokenDep,
    user_fmu_dir: UserFMUDirDep,
    fmu_settings_session: Annotated[str | None, Cookie()] = None,
) -> SessionResponse:
    """Establishes a user session."""
    if fmu_settings_session:
        raise HTTPException(status_code=409, detail="A session already exists")

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
