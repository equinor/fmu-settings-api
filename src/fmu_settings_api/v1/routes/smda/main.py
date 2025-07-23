"""Routes for querying SMDA's API."""

import asyncio
from collections.abc import Generator
from textwrap import dedent

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from fmu.settings.models.smda import (
    CoordinateSystem,
    FieldItem,
)

from fmu_settings_api.deps import (
    ProjectSmdaSessionDep,
    SessionDep,
)
from fmu_settings_api.interfaces import SmdaAPI
from fmu_settings_api.models import Ok
from fmu_settings_api.models.smda import (
    SmdaField,
    SmdaFieldSearchResult,
    SmdaMasterdataResult,
)
from fmu_settings_api.services.smda import (
    get_coordinate_systems,
    get_countries,
    get_discoveries,
    get_strat_column_areas,
)
from fmu_settings_api.v1.responses import GetSessionResponses, inline_add_response


def _add_response_headers(response: Response) -> Generator[None]:
    """Adds headers specific to the /smda route."""
    response.headers["x-upstream-source"] = "SMDA"
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
async def get_health(session: SessionDep) -> Ok:
    """Returns a simple 200 OK if able to query SMDA."""
    # Handled on the route dependency, duplicated for typing
    if session.access_tokens.smda_api is None:
        raise HTTPException(
            status_code=401,
            detail="SMDA access token is not set",
            headers={"x-upstream-source": "SMDA"},
        )

    try:
        smda = SmdaAPI(
            session.access_tokens.smda_api.get_secret_value(),
            session.user_fmu_directory.get_config_value(
                "user_api_keys.smda_subscription"
            ).get_secret_value(),
        )
        await smda.health()
        return Ok()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"SMDA error requesting {e.request.url}",
            headers={"x-upstream-source": "SMDA"},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
            headers={"x-upstream-source": "SMDA"},
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
async def post_field(session: SessionDep, field: SmdaField) -> SmdaFieldSearchResult:
    """Searches for a field identifier in SMDA."""
    if session.access_tokens.smda_api is None:
        raise HTTPException(
            status_code=401,
            detail="SMDA access token is not set",
            headers={"x-upstream-source": "SMDA"},
        )

    try:
        smda = SmdaAPI(
            session.access_tokens.smda_api.get_secret_value(),
            session.user_fmu_directory.get_config_value(
                "user_api_keys.smda_subscription"
            ).get_secret_value(),
        )

        res = await smda.field([field.identifier])
        data = res.json()["data"]
        return SmdaFieldSearchResult(**data)
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"SMDA error requesting {e.request.url!r}",
            headers={"x-upstream-source": "SMDA"},
        ) from e
    except KeyError as e:
        raise HTTPException(
            status_code=500,
            detail="Malformed response from SMDA: no 'data' field present",
            headers={"x-upstream-source": "SMDA"},
        ) from e
    except TimeoutError as e:
        raise HTTPException(
            status_code=503,
            detail="SMDA API request timed out. Please try again.",
            headers={"x-upstream-source": "SMDA"},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
            headers={"x-upstream-source": "SMDA"},
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
    session: ProjectSmdaSessionDep, smda_fields: list[SmdaField]
) -> SmdaMasterdataResult:
    """Queries SMDA masterdata for .fmu project configuration."""
    if not smda_fields:
        raise HTTPException(
            status_code=400, detail="At least one SMDA field must be provided"
        )
    # Handled on the route dependency, duplicated for typing
    if session.access_tokens.smda_api is None:
        raise HTTPException(
            status_code=401,
            detail="SMDA access token is not set",
            headers={"x-upstream-source": "SMDA"},
        )

    # Sorted for tests as sets don't guarantee order
    unique_field_identifiers = sorted({field.identifier for field in smda_fields})
    try:
        smda = SmdaAPI(
            session.access_tokens.smda_api.get_secret_value(),
            session.user_fmu_directory.get_config_value(
                "user_api_keys.smda_subscription"
            ).get_secret_value(),
        )

        # Query initial list of fields (with duplicates removed)
        field_res = await smda.field(
            unique_field_identifiers,
            columns=[
                "country_identifier",
                "identifier",
                "projected_coordinate_system",
                "uuid",
            ],
        )
        field_results = field_res.json()["data"]["results"]
        if not field_results:
            raise HTTPException(
                status_code=404,
                detail=f"No fields found for identifiers: {unique_field_identifiers}",
                headers={"x-upstream-source": "SMDA"},
            )

        field_items = [FieldItem(**field) for field in field_results]
        field_identifiers = [field.identifier for field in field_items]
        country_identifiers = list(
            {field["country_identifier"] for field in field_results}
        )

        async with asyncio.TaskGroup() as tg:
            coordinate_systems_task = tg.create_task(get_coordinate_systems(smda))
            country_task = tg.create_task(get_countries(smda, country_identifiers))
            discovery_task = tg.create_task(get_discoveries(smda, field_identifiers))
            strat_column_task = tg.create_task(
                get_strat_column_areas(smda, field_identifiers)
            )

        country_items = country_task.result()
        discovery_items = discovery_task.result()
        strat_column_items = strat_column_task.result()
        coordinate_systems = coordinate_systems_task.result()

        # We only have one (a primary) coordinate system per field. Just take the first
        # one of the first result as the pre-selected one.
        field_coordinate_system: CoordinateSystem | None = None
        for crs in coordinate_systems:
            if crs.identifier == field_results[0]["projected_coordinate_system"]:
                field_coordinate_system = crs
                break

        if field_coordinate_system is None:
            raise HTTPException(
                status_code=404,
                detail="Projected field coordinate system not found",
                headers={"x-upstream-source": "SMDA"},
            )

        return SmdaMasterdataResult(
            field=field_items,
            country=country_items,
            discovery=discovery_items,
            stratigraphic_columns=strat_column_items,
            field_coordinate_system=field_coordinate_system,
            coordinate_systems=coordinate_systems,
        )
    except HTTPException as e:
        raise e
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"SMDA error requesting {e.request.url}",
            headers={"x-upstream-source": "SMDA"},
        ) from e
    except KeyError as e:
        raise HTTPException(
            status_code=500,
            detail="Malformed response from SMDA: {e}",
            headers={"x-upstream-source": "SMDA"},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
            headers={"x-upstream-source": "SMDA"},
        ) from e
    except TimeoutError as e:
        raise HTTPException(
            status_code=503,
            detail="SMDA API request timed out. Please try again.",
            headers={"x-upstream-source": "SMDA"},
        ) from e
