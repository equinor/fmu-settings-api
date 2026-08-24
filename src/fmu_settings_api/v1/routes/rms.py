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

from fmu_settings_api.deps import (
    ProjectValidationServiceDep,
    RefreshLockDep,
    SessionServiceDep,
    WritePermissionDep,
)
from fmu_settings_api.deps.rms import (
    RmsProjectDep,
    RmsProjectPathDep,
    RmsServiceDep,
)
from fmu_settings_api.models.common import Message
from fmu_settings_api.models.project import ValidationMismatchDetail
from fmu_settings_api.models.rms import RmsVersion
from fmu_settings_api.services.project_validation import RmsProjectMismatchError
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
        dedent("RMS project was not found or its version could not be determined."),
        [
            {
                "detail": (
                    "RMS project does not exist at the "
                    "configured path: {rms_project_path}."
                )
            },
            {
                "detail": (
                    "RMS version cannot be determined because the RMS project "
                    ".master file is not found at {rms_project_path}."
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

RmsProjectValidationResponses: Final[Responses] = {
    **inline_add_response(
        403,
        "The project configuration cannot be accessed for writing.",
        [
            {
                "detail": (
                    "Permission denied accessing .fmu at {project_fmu_directory_path}"
                )
            },
        ],
    ),
    **inline_add_response(
        404,
        dedent(
            """
            The RMS project saved in the FMU project or its .master file could not
            be accessed while determining its version.
            """
        ),
        [
            {"detail": "RMS project not found at '{rms_project_path}'."},
            {
                "detail": (
                    "RMS version cannot be determined because the RMS project "
                    ".master file is not found at {rms_project_path}."
                )
            },
        ],
    ),
    **inline_add_response(
        423,
        "The project is not locked for writing by the current session.",
        [
            {"detail": "Project is not locked. Acquire the lock before writing."},
            {
                "detail": (
                    "Project lock file is missing. Project is treated as read-only."
                )
            },
            {
                "detail": (
                    "Project is read-only. Cannot write to project that is locked "
                    "by another process."
                )
            },
        ],
    ),
    **inline_add_response(
        422,
        dedent(
            """
            The FMU project has no saved RMS settings, the saved settings do not
            match the open RMS project, or the RMS version cannot be used.
            """
        ),
        [
            {"detail": "No RMS settings are saved in the FMU project."},
            {
                "detail": {
                    "message": "Saved RMS settings do not match the open RMS project.",
                    "mismatches": [
                        {
                            "key": "rms.horizons.Top",
                            "saved_value": {
                                "name": "Top",
                                "type": "interpreted",
                            },
                            "source_value": {
                                "name": "Top",
                                "type": "calculated",
                            },
                            "message": (
                                "RMS horizon 'Top' has different settings in the "
                                "FMU project and the open RMS project."
                            ),
                        },
                        {
                            "key": "rms.wells.A-1",
                            "saved_value": {"name": "A-1", "planned": False},
                            "source_value": None,
                            "message": (
                                "RMS well 'A-1' is saved in the FMU project but is "
                                "not present in the open RMS project."
                            ),
                        },
                    ],
                }
            },
            {"detail": "RMS version error for project at '{rms_project_path}'"},
            {"detail": "Failed to validate the open RMS project: {error_message}"},
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
    version = rms_version.version if rms_version is not None else None
    if version is not None and not rms_project_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"RMS project not found at '{rms_project_path}'.",
        )
    try:
        if version is None:
            version = rms_service.get_rms_version(rms_project_path)
        executor, project = rms_service.open_rms_project(rms_project_path, version)
        await session_service.add_rms_session(executor, project)
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
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
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


@router.post(
    "/validate",
    response_model=Message,
    dependencies=[WritePermissionDep, RefreshLockDep],
    summary="Validate saved RMS settings against the open RMS project",
    description=dedent(
        """
        Compare the RMS settings saved in the FMU project with the open RMS
        project.

        The operation does not modify saved RMS settings. When validation
        succeeds, it updates RMS validation metadata in project config.
        """
    ),
    responses={
        **GetSessionResponses,
        **RmsResponses,
        **RmsProjectValidationResponses,
    },
)
async def post_validate_rms_project(
    project_validation_service: ProjectValidationServiceDep,
    rms_service: RmsServiceDep,
    opened_rms_project: RmsProjectDep,
) -> Message:
    """Validate saved RMS configuration against the open RMS project."""
    try:
        project_validation_service.validate_rms_project_and_update_metadata(
            rms_service,
            opened_rms_project,
        )
    except RmsProjectMismatchError as e:
        raise HTTPException(
            status_code=422,
            detail=ValidationMismatchDetail(
                message="Saved RMS settings do not match the open RMS project.",
                mismatches=e.mismatches,
            ).model_dump(),
        ) from e
    except RmsProjectNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RmsVersionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RemoteException as e:
        raise HTTPException(
            status_code=422,
            detail=f"Failed to validate the open RMS project: {e}",
        ) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return Message(message="RMS project configuration validated successfully.")


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
