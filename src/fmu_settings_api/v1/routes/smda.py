"""Routes for querying SMDA's API."""

from textwrap import dedent

from fastapi import APIRouter

from fmu_settings_api.models import Ok
from fmu_settings_api.v1.responses import GetSessionResponses

router = APIRouter(prefix="/smda", tags=["smda"])


@router.get(
    "/check",
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
async def get_check() -> Ok:
    """Returns a simple 200 OK if able to query SMDA."""
    return Ok()
