"""Routes for mappings."""

from textwrap import dedent
from typing import Final

from fastapi import APIRouter, HTTPException
from fmu.datamodels.context.mappings import StratigraphyMappings
from pydantic import ValidationError

from fmu_settings_api.deps.mappings import MappingsServiceDep
from fmu_settings_api.v1.responses import Responses, inline_add_response

router = APIRouter(prefix="/mappings", tags=["mappings"])


@router.get(
    "/stratigraphy",
    response_model=StratigraphyMappings,
    summary="Returns the stratigraphy mappings from the .fmu directory.",
    description=dedent(""""""),
    responses={},
)
async def get_stratigraphy_mappings(
    mappings_service: MappingsServiceDep,
) -> StratigraphyMappings:
    """Returns the stratigraphy mappings from the .fmu directory."""
    try:
        return mappings_service.list_stratigraphy_mappings()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=(
                "The existing mappings resource contains invalid content. "
                f"Validation errors: {e.errors}"
            ),
        ) from e


@router.patch(
    "/stratigraphy",
    response_model=StratigraphyMappings,
    summary="Saves stratigraphy mappings to the project .fmu directory",
    description=dedent(""""""),
    responses={},
)
async def patch_stratigraphy(
    mappings_service: MappingsServiceDep, stratigraphy_mappings: StratigraphyMappings
) -> StratigraphyMappings:
    """Saves stratigraphy mappings to the project .fmu directory."""
    try:
        return mappings_service.update_stratigraphy_mappings(stratigraphy_mappings)
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=(
                "Permission denied while trying to update the stratigraphy mapppings."
            ),
        ) from e
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=(
                "The stratigraphy mappings object to store is invalid."
                f"Validation errors: {e.errors}"
            ),
        ) from e
