"""Routes for matching."""

from textwrap import dedent
from typing import Final

import httpx
from fastapi import APIRouter, HTTPException

from fmu_settings_api.config import HttpHeader
from fmu_settings_api.deps import ProjectSmdaServiceDep
from fmu_settings_api.deps.match import MatchServiceDep
from fmu_settings_api.deps.session import ProjectSessionDep
from fmu_settings_api.models.match import (
    RmsCoordinateSystemMatch,
    RmsStratigraphyMatch,
)
from fmu_settings_api.v1.responses import (
    GetSessionResponses,
    Responses,
    inline_add_response,
)

MatchResponses: Final[Responses] = {
    **inline_add_response(
        400,
        dedent(
            """
            Required configuration is missing from the project config,
            or invalid parameters are provided.
            """
        ),
        [
            {"detail": "RMS zones not found in project configuration"},
            {"detail": "RMS coordinate system not found in project configuration"},
            {"detail": "SMDA masterdata not found in project configuration"},
            {"detail": "Stratigraphic column identifier not found in masterdata"},
        ],
    ),
    **inline_add_response(
        422,
        dedent(
            """
            SMDA returns valid data but no results are found,
            or configuration exists but contains no matchable data.
            """
        ),
        [
            {"detail": "No stratigraphic units found for column: {identifier}"},
            {"detail": "No RMS zones available for matching"},
        ],
    ),
    **inline_add_response(
        500,
        dedent(
            """
            SMDA returns a malformed response that doesn't match
            the expected structure.
            """
        ),
        [
            {"detail": "Malformed response from SMDA: {error_details}"},
        ],
    ),
    **inline_add_response(
        503,
        dedent(
            """
            An API call to SMDA times out or the service is unavailable.
            """
        ),
        [
            {"detail": "SMDA API request timed out. Please try again."},
            {"detail": "SMDA error requesting {url}"},
        ],
    ),
}

router = APIRouter(prefix="/match", tags=["match"])


@router.get(
    "/stratigraphy",
    response_model=list[RmsStratigraphyMatch],
    summary="Match RMS zones to SMDA stratigraphic units",
    description=dedent(
        """
        Match RMS stratigraphic zones to SMDA stratigraphic units using a
        greedy matching algorithm based on name similarity.

        This endpoint automatically fetches:
        - RMS zones from the project configuration
        - SMDA stratigraphic units using the stratigraphic column identifier
          from the project's masterdata configuration

        The algorithm uses token-sort ratio for flexible name matching
        that allows different word ordering.

        Confidence levels:
        - 'high': score > 80
        - 'medium': score 50-80
        - 'low': score < 50

        Requirements:
        - Project config must contain rms.zones
        - Project config must contain masterdata.smda.stratigraphic_column.identifier
        """
    ),
    responses={
        **GetSessionResponses,
        **MatchResponses,
    },
)
async def get_stratigraphy(
    match_service: MatchServiceDep,
    smda_service: ProjectSmdaServiceDep,
    project_session: ProjectSessionDep,
) -> list[RmsStratigraphyMatch]:
    """Match RMS zones to SMDA stratigraphic units.

    This endpoint fetches both RMS zones and SMDA stratigraphic units
    from the project configuration and returns the matching results.
    """
    try:
        return await match_service.match_stratigraphy_from_config_to_smda(
            project_session, smda_service
        )
    except ValueError as e:
        error_msg = str(e)
        status_code = 422 if "No stratigraphic units found" in error_msg else 400
        raise HTTPException(
            status_code=status_code,
            detail=error_msg,
            headers={HttpHeader.UPSTREAM_SOURCE_KEY: HttpHeader.UPSTREAM_SOURCE_SMDA},
        ) from e
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"SMDA error requesting {e.request.url}",
            headers={HttpHeader.UPSTREAM_SOURCE_KEY: HttpHeader.UPSTREAM_SOURCE_SMDA},
        ) from e
    except KeyError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Malformed response from SMDA: {e}",
            headers={HttpHeader.UPSTREAM_SOURCE_KEY: HttpHeader.UPSTREAM_SOURCE_SMDA},
        ) from e
    except TimeoutError as e:
        raise HTTPException(
            status_code=503,
            detail="SMDA API request timed out. Please try again.",
            headers={HttpHeader.UPSTREAM_SOURCE_KEY: HttpHeader.UPSTREAM_SOURCE_SMDA},
        ) from e


@router.get(
    "/coordinate_system",
    response_model=RmsCoordinateSystemMatch,
    summary="Match RMS coordinate system to SMDA coordinate systems",
    description=dedent(
        """
        Match RMS coordinate system to SMDA coordinate system using
        name similarity.

        This endpoint automatically fetches:
        - RMS coordinate system from the project configuration
        - SMDA coordinate system from the project's masterdata configuration

        The algorithm uses strict ratio matching for coordinate system names.

        Confidence levels:
        - 'high': score > 80
        - 'medium': score 50-80
        - 'low': score < 50

        Requirements:
        - Project config must contain rms.coordinate_system
        - Project config must contain masterdata.smda.coordinate_system
        """
    ),
    responses={
        **GetSessionResponses,
        **inline_add_response(
            400,
            "Required configuration is missing from the project config.",
            [
                {"detail": "RMS coordinate system not found in project configuration"},
                {"detail": "SMDA coordinate system not found in masterdata"},
            ],
        ),
    },
)
async def get_coordinate_system(
    match_service: MatchServiceDep,
    project_session: ProjectSessionDep,
) -> RmsCoordinateSystemMatch:
    """Match RMS coordinate system to SMDA coordinate system.

    This endpoint fetches both RMS and SMDA coordinate systems
    from the project configuration and returns the matching result.
    """
    try:
        return match_service.match_coordinate_system_from_config_to_smda(
            project_session
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        ) from e
