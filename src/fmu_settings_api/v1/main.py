"""The main router for /api/v1."""

from fastapi import APIRouter, Depends

from fmu_settings_api.config import settings
from fmu_settings_api.deps import get_session, get_smda_session
from fmu_settings_api.models import Ok
from fmu_settings_api.v1.responses import GetSessionResponses

from .routes import project, session, smda, user

api_v1_router = APIRouter(prefix=settings.API_V1_PREFIX, tags=["v1"])

api_v1_router.include_router(project.router, dependencies=[Depends(get_session)])
api_v1_router.include_router(user.router, dependencies=[Depends(get_session)])
api_v1_router.include_router(session.router)
api_v1_router.include_router(smda.router, dependencies=[Depends(get_smda_session)])


@api_v1_router.get(
    "/health",
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
