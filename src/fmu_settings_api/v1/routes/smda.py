"""Routes for querying SMDA's API."""

from textwrap import dedent

from fastapi import APIRouter, HTTPException

from fmu_settings_api.deps import SessionDep
from fmu_settings_api.interfaces import SmdaAPI
from fmu_settings_api.models import Ok
from fmu_settings_api.v1.responses import GetSessionResponses

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
