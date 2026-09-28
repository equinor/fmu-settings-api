"""Routes for Sumo assets and login."""

from typing import Final

from fastapi import APIRouter, HTTPException

from fmu_settings_api.deps import SumoServiceDep
from fmu_settings_api.interfaces import (
    SumoAuthenticationRequiredError,
    SumoInvalidResponseError,
    SumoUnavailableError,
)
from fmu_settings_api.models.common import Ok
from fmu_settings_api.models.sumo import SumoAsset
from fmu_settings_api.v1.responses import (
    GetSessionResponses,
    Responses,
    inline_add_response,
)

router = APIRouter(prefix="/sumo", tags=["sumo"])

SumoAssetsResponses: Final[Responses] = {
    **inline_add_response(
        424,
        "Sumo login required",
        [{"detail": "Sumo login is required"}],
    ),
    **inline_add_response(
        502,
        "Invalid response from Sumo",
        [{"detail": "Sumo returned an invalid asset response"}],
    ),
    **inline_add_response(
        503,
        "Sumo unavailable",
        [{"detail": "Unable to get assets from Sumo"}],
    ),
}

SumoLoginResponses: Final[Responses] = {
    **inline_add_response(
        424,
        "Sumo login not completed",
        [{"detail": "Sumo login was not completed"}],
    ),
    **inline_add_response(
        503,
        "Sumo unavailable",
        [{"detail": "Unable to connect to Sumo"}],
    ),
}


@router.get(
    "/assets",
    response_model=list[SumoAsset],
    summary="Returns Sumo assets with user write access.",
    description="Returns assets to which the current user has write access.",
    responses={**GetSessionResponses, **SumoAssetsResponses},
)
def get_assets(sumo_service: SumoServiceDep) -> list[SumoAsset]:
    """Return the Sumo assets to which the user has write access."""
    try:
        return sumo_service.get_assets()
    except SumoAuthenticationRequiredError as e:
        raise HTTPException(status_code=424, detail=str(e)) from e
    except SumoInvalidResponseError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except SumoUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.post(
    "/login",
    response_model=Ok,
    summary="Logs in to Sumo.",
    description="Starts an interactive Sumo login if no cached token is available.",
    responses={**GetSessionResponses, **SumoLoginResponses},
)
def post_login(sumo_service: SumoServiceDep) -> Ok:
    """Log in to Sumo interactively."""
    try:
        sumo_service.login()
        return Ok()
    except SumoAuthenticationRequiredError as e:
        raise HTTPException(status_code=424, detail=str(e)) from e
    except SumoUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
