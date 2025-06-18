"""The main router for /api/v1."""

from fastapi import APIRouter, Depends

from fmu_settings_api.deps import get_session, get_smda_session
from fmu_settings_api.models import Ok
from fmu_settings_api.v1.responses import GetSessionResponses

from .routes import project, session, user
from .routes.smda import main as smda

api_v1_router = APIRouter()
api_v1_router.include_router(project.router, dependencies=[Depends(get_session)])
api_v1_router.include_router(user.router, dependencies=[Depends(get_session)])
api_v1_router.include_router(session.router)
api_v1_router.include_router(smda.router, dependencies=[Depends(get_smda_session)])


@api_v1_router.get(
    "/health",
    tags=["health"],
    response_model=Ok,
    dependencies=[Depends(get_session)],
    summary="A health check on the /v1 routes.",
    description=(
        "This route requires a valid session to return 200 OK. it can used to "
        "check if the user has a valid session."
    ),
    responses=GetSessionResponses,
)
async def v1_health_check() -> Ok:
    """Simple health check endpoint."""
    return Ok()
