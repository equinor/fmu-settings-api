"""Routes for querying SMDA's API."""

from collections.abc import Generator
from textwrap import dedent

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response

from fmu_settings_api.config import HttpHeader
from fmu_settings_api.deps import (
    ProjectSmdaServiceDep,
    SmdaServiceDep,
)
from fmu_settings_api.models import Ok
from fmu_settings_api.models.smda import (
    SmdaField,
    SmdaFieldSearchResult,
    SmdaMasterdataResult,
)
from fmu_settings_api.v1.responses import GetSessionResponses, inline_add_response


def _add_response_headers(response: Response) -> Generator[None]:
    """Adds headers specific to the /smda route."""
    response.headers[HttpHeader.UPSTREAM_SOURCE_KEY] = HttpHeader.UPSTREAM_SOURCE_SMDA
    yield


router = APIRouter(
    prefix="/smda", tags=["smda"], dependencies=[Depends(_add_response_headers)]
)


@router.get(
    "/health",
    response_model=Ok,
    summary="Checks whether or not the current session is capable of querying SMDA",
    description=dedent(
        """
        A route to check whether the client is capable of querying SMDA APIs
        with their current session. The requirements for querying the SMDA API via
        this API are:

        1. A valid session
        2. An SMDA subscription key in the user's .fmu API key configuration
        3. A valid SMDA access token scoped to SMDA's user_impersonation scope

        A successful response from this route indicates that all other routes on the
        SMDA router can be used."""
    ),
    responses={
        **GetSessionResponses,
    },
)
async def get_health(smda_service: SmdaServiceDep) -> Ok:
    """Returns a simple 200 OK if able to query SMDA."""
    try:
        await smda_service.check_health()
        return Ok()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"SMDA error requesting {e.request.url}",
            headers={HttpHeader.UPSTREAM_SOURCE_KEY: HttpHeader.UPSTREAM_SOURCE_SMDA},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
            headers={HttpHeader.UPSTREAM_SOURCE_KEY: HttpHeader.UPSTREAM_SOURCE_SMDA},
        ) from e


@router.post(
    "/field",
    response_model=SmdaFieldSearchResult,
    summary="Searches for a field identifier in SMDA",
    description=dedent(
        """
        A route to search SMDA for an field (asset) by its named identifier.

        This endpoint applies a projection to the SMDA query so that only the relevant
        data is returned: an identifier known by SMDA and its corresponding UUID. The
        UUID should be used by other endpoints required the collection of data by a
        field, i.e. this route is a dependency for most other routes.

        The number of results (hits) and number of pages those results span over is also
        returned in the result. This endpoint does not implement pagination. The
        current expectation is that a user would refine their search rather than page
        through different results.
        """
    ),
    responses={
        **GetSessionResponses,
    },
)
async def post_field(
    smda_service: SmdaServiceDep, field: SmdaField
) -> SmdaFieldSearchResult:
    """Searches for a field identifier in SMDA."""
    try:
        return await smda_service.search_field(field)
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"SMDA error requesting {e.request.url!r}",
            headers={HttpHeader.UPSTREAM_SOURCE_KEY: HttpHeader.UPSTREAM_SOURCE_SMDA},
        ) from e
    except KeyError as e:
        raise HTTPException(
            status_code=500,
            detail="Malformed response from SMDA: no 'data' field present",
            headers={HttpHeader.UPSTREAM_SOURCE_KEY: HttpHeader.UPSTREAM_SOURCE_SMDA},
        ) from e
    except TimeoutError as e:
        raise HTTPException(
            status_code=503,
            detail="SMDA API request timed out. Please try again.",
            headers={HttpHeader.UPSTREAM_SOURCE_KEY: HttpHeader.UPSTREAM_SOURCE_SMDA},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
            headers={HttpHeader.UPSTREAM_SOURCE_KEY: HttpHeader.UPSTREAM_SOURCE_SMDA},
        ) from e


@router.post(
    "/masterdata",
    response_model=SmdaMasterdataResult,
    summary="Retrieves masterdata for fields to be confirmed in the GUI",
    description=dedent(
        """
        A route to gather prospective SMDA masterdata relevant to FMU.

        This route receives a list of valid field names and returns masterdata that
        pertains to them. The field names should be valid as return from from the
        `smda/field` routes.

        The data returned from this endpoint is meant to be confirmed by the user who
        may need to do some additional selection or pruning based upon the model they
        are working from.

        One example of this is changing the coordinate system. A model may use a
        coordinate system different from the one set as the field's default coordinate
        system in SMDA. To match the way this works on SMDA, every coordinate system
        known to SMDA is returned.

        This endpoint does multiple calls to the SMDA API, any of which may possibly
        fail. In any of these calls fails incomplete data will _not_ be returned; that
        is, a successful code with partial data will not be returned.
        """
    ),
    responses={
        **GetSessionResponses,
        **inline_add_response(
            503,
            "Occurs when an API call to SMDA times out.",
            [
                {"detail": "SMDA API request timed out. Please try again."},
            ],
        ),
    },
)
async def post_masterdata(
    smda_fields: list[SmdaField],
    smda_service: ProjectSmdaServiceDep,
) -> SmdaMasterdataResult:
    """Queries SMDA masterdata for .fmu project configuration."""
    try:
        return await smda_service.get_masterdata(smda_fields)
    except ValueError as e:
        error_msg = str(e)
        match error_msg:
            case msg if "At least one SMDA field must be provided" in msg:
                status_code = 400
            case msg if "No fields found for identifiers" in msg:
                status_code = 422
            case msg if "not found in SMDA" in msg:
                status_code = 404
            case _:
                status_code = 400
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
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
            headers={HttpHeader.UPSTREAM_SOURCE_KEY: HttpHeader.UPSTREAM_SOURCE_SMDA},
        ) from e
