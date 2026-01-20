"""Routes for interacting with RMS projects."""

from textwrap import dedent
from typing import Final

from fastapi import APIRouter, HTTPException
from fmu.settings.models.project_config import (
    RmsCoordinateSystem,
    RmsHorizon,
    RmsStratigraphicZone,
    RmsWell,
)
from runrms.api.proxy import RemoteException
from runrms.exceptions import RmsProjectNotFoundError, RmsVersionError

from fmu_settings_api.deps import SessionServiceDep
from fmu_settings_api.deps.rms import (
    RmsProjectDep,
    RmsProjectPathDep,
    RmsServiceDep,
)
from fmu_settings_api.models.common import Message
from fmu_settings_api.models.rms import RmsVersion
from fmu_settings_api.session import (
    SessionNotFoundError,
)
from fmu_settings_api.v1.responses import (
    GetSessionResponses,
    Responses,
    inline_add_response,
)

RmsResponses: Final[Responses] = {
    **inline_add_response(
        400,
        dedent(
            """
            RMS project path is not configured in the project config file,
            or no RMS project is currently open in the session.
            """
        ),
        [
            {"detail": "RMS project path is not set in the project config file."},
            {
                "detail": (
                    "No RMS project is currently open. "
                    "Please open an RMS project first."
                )
            },
        ],
    ),
}

FailedOpeningRmsProjectResponses: Final[Responses] = {
    **inline_add_response(
        400,
        dedent("RMS project path is not configured in the project config file."),
        [
            {"detail": "RMS project path is not set in the project config file."},
        ],
    ),
    **inline_add_response(
        404,
        dedent("RMS project does not exist at the configured path."),
        [
            {
                "detail": (
                    "RMS project does not exist at the "
                    "configured path: {rms_project_path}."
                )
            },
        ],
    ),
    **inline_add_response(
        422,
        dedent("Failed to open RMS project {rms_project_path}."),
        [
            {"detail": "Could not open project using RMS version {version}."},
            {"detail": "Unable to check out required license."},
            {
                "detail": (
                    "Failed setting up RMS API proxy: The requested RMS version "
                    "{version} is not supported. Try specifying another RMS version "
                    "or upgrade the RMS project."
                )
            },
        ],
    ),
}

router = APIRouter(prefix="/rms", tags=["rms"])


@router.post(
    "/",
    response_model=Message,
    summary="Open an RMS project and store it in the session",
    description=dedent(
        """
        Open an RMS project and store it in the session.

        The RMS project path must be configured in the project's .fmu config file.
        Once opened, the project remains open in the session until explicitly closed
        or the session expires. This allows for efficient repeated access without
        reopening the project each time.

        The endpoint takes an optional parameter, `rms_version`, as input. This can be
        used to specify which version of RMS API that should be used when opening
        the RMS project.
        """
    ),
    responses={
        **GetSessionResponses,
        **FailedOpeningRmsProjectResponses,
    },
)
async def post_rms_project(
    rms_service: RmsServiceDep,
    session_service: SessionServiceDep,
    rms_project_path: RmsProjectPathDep,
    rms_version: RmsVersion | None = None,
) -> Message:
    """Open an RMS project and store it in the session."""
    try:
        version = (
            rms_version.version
            if rms_version is not None
            else rms_service.get_rms_version(rms_project_path)
        )
        root_proxy, project = rms_service.open_rms_project(rms_project_path, version)
        await session_service.add_rms_session(root_proxy, project)
        return Message(
            message=f"RMS project opened successfully with RMS version {version}."
        )
    except SessionNotFoundError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except RmsProjectNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=(
                "RMS project does not exist at the "
                f"configured path: {rms_project_path}."
            ),
        ) from e
    except RmsVersionError as e:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Failed to open RMS project {rms_project_path}: "
                f"Failed setting up RMS API proxy: The requested RMS version {version} "
                "is not supported. Try specifying another RMS version "
                "or upgrading the RMS project."
            ),
        ) from e
    except RemoteException as e:
        error_msg_base = f"Failed to open RMS project {rms_project_path}: "
        if "File version" in str(e) and "is not supported" in str(e):
            error_msg = error_msg_base + (
                f"Could not open project using RMS version {version}: {str(e)}"
            )
        elif "Unable to check out required license." in str(e):
            error_msg = error_msg_base + (
                f"Unable to check out required license: {str(e)}"
            )
        else:
            error_msg = error_msg_base + f"{str(e)}"
        raise HTTPException(status_code=422, detail=error_msg) from e


@router.delete(
    "/",
    response_model=Message,
    summary="Close the RMS project in the session",
    responses=GetSessionResponses,
)
async def delete_rms_project(session_service: SessionServiceDep) -> Message:
    """Close the RMS project that is currently open in the session.

    This removes the RMS project reference from the session. The project
    should be closed when it is no longer needed to free up resources.
    """
    try:
        await session_service.remove_rms_session()
        return Message(message="RMS project closed successfully")
    except SessionNotFoundError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


@router.get(
    "/zones",
    response_model=list[RmsStratigraphicZone],
    summary="Get the zones from the open RMS project",
    responses={
        **GetSessionResponses,
        **RmsResponses,
    },
)
async def get_zones(
    rms_service: RmsServiceDep,
    opened_rms_project: RmsProjectDep,
) -> list[RmsStratigraphicZone]:
    """Retrieve the zones from the currently open RMS project.

    This endpoint requires an RMS project to be open in the session.
    Use the POST / endpoint first to open an RMS project.
    """
    return rms_service.get_zones(opened_rms_project)


@router.get(
    "/horizons",
    response_model=list[RmsHorizon],
    summary="Get all horizons from the open RMS project",
    responses={
        **GetSessionResponses,
        **RmsResponses,
    },
)
async def get_horizons(
    rms_service: RmsServiceDep,
    opened_rms_project: RmsProjectDep,
) -> list[RmsHorizon]:
    """Retrieve all horizons from the currently open RMS project.

    This endpoint requires an RMS project to be open in the session.
    Use the POST / endpoint first to open an RMS project.
    """
    return rms_service.get_horizons(opened_rms_project)


@router.get(
    "/wells",
    response_model=list[RmsWell],
    summary="Get all wells from the open RMS project",
    responses={
        **GetSessionResponses,
        **RmsResponses,
    },
)
async def get_wells(
    rms_service: RmsServiceDep,
    opened_rms_project: RmsProjectDep,
) -> list[RmsWell]:
    """Retrieve all wells from the currently open RMS project.

    This endpoint requires an RMS project to be open in the session.
    Use the POST / endpoint first to open an RMS project.
    """
    return rms_service.get_wells(opened_rms_project)


@router.get(
    "/coordinate_system",
    response_model=RmsCoordinateSystem,
    summary="Get the project coordinate system from the open RMS project",
    responses={
        **GetSessionResponses,
        **RmsResponses,
    },
)
async def get_coordinate_system(
    rms_service: RmsServiceDep,
    opened_rms_project: RmsProjectDep,
) -> RmsCoordinateSystem:
    """Retrieve the project coordinate system from the currently open RMS project.

    This endpoint requires an RMS project to be open in the session.
    Use the POST / endpoint first to open an RMS project.
    """
    return rms_service.get_coordinate_system(opened_rms_project)
