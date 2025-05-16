"""The main router for /api/v1."""

from fastapi import APIRouter, Depends

from fmu_settings_api.config import settings
from fmu_settings_api.deps import verify_auth_token

from .routes import config, fmu, user

api_v1_router = APIRouter(
    prefix=settings.API_V1_PREFIX,
    tags=["v1"],
    dependencies=[Depends(verify_auth_token)],
)
api_v1_router.include_router(fmu.router)
api_v1_router.include_router(config.router)
api_v1_router.include_router(user.router)


@api_v1_router.get("/health")
async def v1_health_check() -> dict[str, str]:
    """Simple health check endpoint."""
    return {"status": "ok"}
