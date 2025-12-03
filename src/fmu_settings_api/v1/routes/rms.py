"""Routes for interacting with RMS projects."""

from fastapi import APIRouter, HTTPException

from fmu_settings_api.deps.rms import (
    RmsProjectDep,
    RmsProjectPathDep,
    RmsServiceDep,
)
from fmu_settings_api.deps.session import ProjectSessionDep
from fmu_settings_api.models.common import Message
from fmu_settings_api.models.rms import (
    RmsHorizonList,
    RmsWellList,
    RmsZoneList,
)
from fmu_settings_api.session import (
    SessionNotFoundError,
    add_rms_project_to_session,
    remove_rms_project_from_session,
)
from fmu_settings_api.v1.responses import GetSessionResponses

router = APIRouter(prefix="/rms", tags=["rms"])


@router.post(
    "/",
    response_model=Message,
    summary="Open an RMS project and store it in the session",
    responses=GetSessionResponses,
)
async def post_rms_project(
    rms_service: RmsServiceDep,
    project_session: ProjectSessionDep,
    rms_project_path: RmsProjectPathDep,
) -> Message:
    """Open an RMS project and store it in the session.

    The RMS project path must be configured in the project's .fmu config file.
    Once opened, the project remains open in the session until explicitly closed
    or the session expires. This allows for efficient repeated access without
    reopening the project each time.
    """
    try:
        opened_project = rms_service.open_rms_project(rms_project_path)
        rms_version = rms_service.get_rms_version(rms_project_path)
        await add_rms_project_to_session(project_session.id, opened_project)
        return Message(
            message=f"RMS project opened successfully with RMS version {rms_version}"
        )
    except SessionNotFoundError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


@router.delete(
    "/",
    response_model=Message,
    summary="Close the RMS project in the session",
    responses=GetSessionResponses,
)
async def delete_rms_project(
    project_session: ProjectSessionDep,
) -> Message:
    """Close the RMS project that is currently open in the session.

    This removes the RMS project reference from the session. The project
    should be closed when it is no longer needed to free up resources.
    """
    try:
        await remove_rms_project_from_session(project_session.id)
        return Message(message="RMS project closed successfully")
    except SessionNotFoundError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


@router.get(
    "/zones",
    response_model=RmsZoneList,
    summary="Get the zones from the open RMS project",
    responses=GetSessionResponses,
)
async def get_zones(
    rms_service: RmsServiceDep,
    opened_rms_project: RmsProjectDep,
) -> RmsZoneList:
    """Retrieve the zones from the currently open RMS project.

    This endpoint requires an RMS project to be open in the session.
    Use the POST / endpoint first to open an RMS project.
    """
    return rms_service.get_zones(opened_rms_project)


@router.get(
    "/horizons",
    response_model=RmsHorizonList,
    summary="Get all horizons from the open RMS project",
    responses=GetSessionResponses,
)
async def get_horizons(
    rms_service: RmsServiceDep,
    opened_rms_project: RmsProjectDep,
) -> RmsHorizonList:
    """Retrieve all horizons from the currently open RMS project.

    This endpoint requires an RMS project to be open in the session.
    Use the POST / endpoint first to open an RMS project.
    """
    return rms_service.get_horizons(opened_rms_project)


@router.get(
    "/wells",
    response_model=RmsWellList,
    summary="Get all wells from the open RMS project",
    responses=GetSessionResponses,
)
async def get_wells(
    rms_service: RmsServiceDep,
    opened_rms_project: RmsProjectDep,
) -> RmsWellList:
    """Retrieve all wells from the currently open RMS project.

    This endpoint requires an RMS project to be open in the session.
    Use the POST / endpoint first to open an RMS project.
    """
    return rms_service.get_wells(opened_rms_project)
