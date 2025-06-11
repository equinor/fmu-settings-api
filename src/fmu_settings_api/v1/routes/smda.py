"""Routes for querying SMDA's API."""

from textwrap import dedent

from fastapi import APIRouter, HTTPException

from fmu_settings_api.deps import SessionDep
from fmu_settings_api.interfaces import SmdaAPI
from fmu_settings_api.models import Ok
from fmu_settings_api.models.smda import (
    SMDAField,
    SMDAFieldSearchResult,
)
from fmu_settings_api.v1.responses import GetSessionResponses, add_response_example

router = APIRouter(prefix="/smda", tags=["smda"])


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
async def get_health(session: SessionDep) -> Ok:
    """Returns a simple 200 OK if able to query SMDA."""
    # Handled on the route dependency, duplicated for typing
    if session.access_tokens.smda_api is None:
        raise HTTPException(status_code=401, detail="SMDA access token is not set")

    try:
        smda = SmdaAPI(
            session.access_tokens.smda_api.get_secret_value(),
            session.user_fmu_directory.get_config_value(
                "user_api_keys.smda_subscription"
            ).get_secret_value(),
        )
        await smda.health()
        return Ok()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/field",
    response_model=SMDAFieldSearchResult,
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
        **add_response_example(
            GetSessionResponses,
            500,
            {"detail": "Malformed response from SMDA: no 'data' field present"},
        )
    },
)
async def post_field(session: SessionDep, field: SMDAField) -> SMDAFieldSearchResult:
    """Searches for a field identifier in SMDA."""
    if session.access_tokens.smda_api is None:
        raise HTTPException(status_code=401, detail="SMDA access token is not set")

    try:
        smda = SmdaAPI(
            session.access_tokens.smda_api.get_secret_value(),
            session.user_fmu_directory.get_config_value(
                "user_api_keys.smda_subscription"
            ).get_secret_value(),
        )

        res = await smda.field(field.identifier)
        data = res.json().get("data", None)

        if not data:
            # It is most likely that SMDA never responded than its response is
            # malformed so this check is probably unnecessary. Included because a
            # keyvalue error on res.json()["data"] is more confusing than this.
            raise HTTPException(
                status_code=500,
                detail="Malformed response from SMDA: no 'data' field present",
            )

        return SMDAFieldSearchResult(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
