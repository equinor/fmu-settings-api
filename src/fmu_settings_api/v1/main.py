"""The main router for /api/v1."""

import contextlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from fmu.settings import find_nearest_fmu_directory
from fmu.settings.models.user_config import UserConfig

from fmu_settings_api.config import settings
from fmu_settings_api.deps import (
    AuthTokenDep,
    UserFMUDirDep,
    get_session,
    verify_auth_token,
)
from fmu_settings_api.models import FMUProject, SessionResponse
from fmu_settings_api.session import (
    add_fmu_project_to_session,
    create_fmu_session,
)

from .routes import project, user

api_v1_router = APIRouter(prefix=settings.API_V1_PREFIX, tags=["v1"])

api_v1_router.include_router(project.router, dependencies=[Depends(get_session)])
api_v1_router.include_router(user.router, dependencies=[Depends(get_session)])


@api_v1_router.get("/health", dependencies=[Depends(get_session)])
async def v1_health_check() -> dict[str, str]:
    """Simple health check endpoint."""
    return {"status": "ok"}


@api_v1_router.post(
    "/session",
    response_model=SessionResponse,
    dependencies=[Depends(verify_auth_token)],
)
async def create_session(
    response: Response, auth_token: AuthTokenDep, user_fmu_dir: UserFMUDirDep
) -> SessionResponse:
    """Establishes a user session."""
    try:
        session_id = await create_fmu_session(user_fmu_dir)
        response.set_cookie(
            key=settings.SESSION_COOKIE_KEY,
            value=session_id,
            httponly=True,
            secure=True,
            samesite="lax",
        )
        config_dict = user_fmu_dir.config.load().model_dump()

        # Overwrite secret keys with obfuscated keys
        for k, v in config_dict["user_api_keys"].items():
            if v is not None:
                # Convert SecretStr("*********") to "*********"
                config_dict["user_api_keys"][k] = str(v)

        user_config = UserConfig.model_validate(config_dict)

        session_response = SessionResponse(user_config=user_config)

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
