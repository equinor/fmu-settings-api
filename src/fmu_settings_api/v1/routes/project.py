"""Routes to add an FMU project to an existing session."""

import json
from pathlib import Path
from textwrap import dedent
from typing import Final

from fastapi import APIRouter, HTTPException, Request
from fmu.datamodels.common import Access, Smda
from fmu.datamodels.context.mappings import (
    DataSystem,
    MappingType,
)
from fmu.datamodels.fmu_results.fields import Model
from fmu.settings import (
    REQUIRED_FMU_PROJECT_SUBDIRS,
    CacheResource,
    InternalMappings,
    InternalStratigraphyMappings,
    InternalWellboreMappings,
    InvalidFMUProjectPathError,
    InvalidGlobalConfigurationError,
    ProjectFMUDirectory,
)
from fmu.settings.models.change_info import ChangeInfo
from fmu.settings.models.diff import ResourceDiff
from fmu.settings.models.log import Log
from fmu.settings.models.project_config import (
    RmsCoordinateSystem,
    RmsWell,
)
from pydantic import TypeAdapter, ValidationError
from runrms.exceptions import RmsVersionError

from fmu_settings_api.deps import (
    ProjectServiceDep,
    ProjectServiceForRestoreDep,
    ProjectSessionServiceDep,
    RefreshLockDep,
    ResourceServiceDep,
    SessionServiceDep,
    WritePermissionDep,
)
from fmu_settings_api.deps.changelog import ChangelogFiltersDep, ChangelogServiceDep
from fmu_settings_api.deps.mappings import MappingsServiceDep
from fmu_settings_api.models import (
    ConfigurationErrorDetail,
    FMUDirPath,
    FMUProject,
    Message,
    RestorableFilesResponse,
    ValidationErrorDetail,
)
from fmu_settings_api.models.common import Ok
from fmu_settings_api.models.project import (
    CacheRetention,
    GlobalConfigPath,
    LockStatus,
    SumoAsset,
)
from fmu_settings_api.models.resource import CacheContent, CacheList
from fmu_settings_api.models.rms import (
    RmsProjectPath,
    RmsProjectPathsResult,
    RmsStratigraphicFramework,
)
from fmu_settings_api.services.project import ProjectService
from fmu_settings_api.session import SessionNotFoundError
from fmu_settings_api.v1.responses import (
    GetSessionResponses,
    Responses,
    inline_add_response,
)

router = APIRouter(prefix="/project", tags=["project"])
REQUIRED_PROJECT_DIRS_TEXT = ", ".join(
    f"'{dir_name}'" for dir_name in REQUIRED_FMU_PROJECT_SUBDIRS
)

ProjectResponses: Final[Responses] = {
    **inline_add_response(
        403,
        "The OS returned a permissions error while locating or creating .fmu",
        [
            {"detail": "Permission denied locating .fmu"},
            {"detail": "Permission denied accessing .fmu at {path}"},
            {"detail": "Permission denied creating .fmu at {path}"},
        ],
    ),
    **inline_add_response(
        404,
        dedent(
            """
            The .fmu directory was unable to be found at or above a given path, or
            the requested path to create a project .fmu directory at does not exist.
            """
        ),
        [
            {"detail": "No .fmu directory found from {path}"},
            {"detail": "No .fmu directory found at {path}"},
            {"detail": "Path {path} does not exist"},
            {"detail": "Project .fmu directory not found. It may have been deleted."},
        ],
    ),
}

ProjectExistsResponses: Final[Responses] = {
    **inline_add_response(
        409,
        dedent(
            """
            A project .fmu directory already exist at a given location, or may
            possibly not be a directory, i.e. it may be a .fmu file.
            """
        ),
        [
            {"detail": ".fmu exists at {path} but is not a directory"},
            {"detail": ".fmu already exists at {path}"},
        ],
    ),
}

ProjectInitResponses: Final[Responses] = {
    **ProjectResponses,
    **ProjectExistsResponses,
    **inline_add_response(
        422,
        "The requested path exists but is not a valid FMU project root.",
        [
            {
                "detail": (
                    "Failed initializing .fmu directory. Initialize it from a "
                    f"project root containing {REQUIRED_PROJECT_DIRS_TEXT}. "
                    "Did not find: {missing_project_dirs}."
                ),
            },
        ],
    ),
}

LockConflictResponses: Final[Responses] = {
    **inline_add_response(
        423,
        dedent(
            """
            The project is locked by another process and cannot be modified.
            The project can still be read but write operations are blocked.
            """
        ),
        [
            {"detail": "Project lock conflict: {error_message}"},
            {
                "detail": (
                    "Project is read-only. Cannot write to project "
                    "that is locked by another process."
                )
            },
        ],
    ),
}

GlobalConfigResponses: Final[Responses] = {
    **inline_add_response(
        404,
        dedent(
            """
            The global config file was not found at a given location.
            """
        ),
        [
            {"detail": "No file exists at path {global_config_path}."},
        ],
    ),
    **inline_add_response(
        409,
        dedent(
            """
            The project .fmu config already contains masterdata.
            """
        ),
        [
            {
                "detail": "A config file with masterdata "
                "already exists in .fmu at {fmu_dir.config.path}."
            },
        ],
    ),
    **inline_add_response(
        422,
        dedent(
            """
            The global config file did not validate against the
            GlobalConfiguration Pydantic model.
            """
        ),
        [
            {"detail": "{A dict with 'message' and 'validation_errors'"},
        ],
    ),
}


RmsConfigNotSetResponses: Final[Responses] = {
    **inline_add_response(
        422,
        dedent(
            """
            RMS project path must be set before updating RMS fields.
            """
        ),
        [
            {
                "detail": "RMS project path must be set before updating RMS fields. "
                "Use PATCH /project/rms first."
            },
        ],
    ),
}

RmsStratigraphicFrameworkResponses: Final[Responses] = {
    **inline_add_response(
        422,
        dedent(
            """
            The RMS stratigraphic framework did not validate.
            """
        ),
        [
            {
                "detail": (
                    "Validation error: RMS zones reference horizons not present in "
                    "request: {horizon_names}"
                )
            },
        ],
    ),
}


MappingsResponses: Final[Responses] = {
    **inline_add_response(
        400,
        "Invalid mapping data or unsupported mapping type",
        [
            {"detail": "Mapping type '{mapping_type}' is not yet supported"},
        ],
    ),
    **inline_add_response(
        404,
        "Project mappings could not be updated because the project path was missing",
        [{"detail": "Project .fmu directory not found. It may have been deleted."}],
    ),
    **inline_add_response(
        422,
        dedent(
            """
            Mappings resource contains invalid content or corrupted JSON.
            """
        ),
        [
            {"detail": "Invalid mappings in existing file: {error_message}"},
            {
                "detail": (
                    "Mappings were not updated because the project contains "
                    "invalid saved mappings."
                )
            },
            {"detail": "Invalid mappings: {error_message}"},
        ],
    ),
}

GetMappingsResponses: Final[Responses] = {
    200: {
        "description": "Mappings for the requested mapping type.",
        "content": {
            "application/json": {
                "example": {
                    "stratigraphy": [
                        {
                            "source_system": "rms",
                            "target_system": "rms",
                            "mapping_type": "stratigraphy",
                            "relation_type": "primary",
                            "source_id": "TopVolantis",
                            "source_uuid": None,
                            "target_id": "TopVolantis",
                            "target_uuid": None,
                        },
                        {
                            "source_system": "rms",
                            "target_system": "rms",
                            "mapping_type": "stratigraphy",
                            "relation_type": "alias",
                            "source_id": "TOP_VOLANTIS",
                            "source_uuid": None,
                            "target_id": "TopVolantis",
                            "target_uuid": None,
                        },
                        {
                            "source_system": "rms",
                            "target_system": "smda",
                            "mapping_type": "stratigraphy",
                            "relation_type": "primary",
                            "source_id": "TopVolantis",
                            "source_uuid": None,
                            "target_id": "VOLANTIS GP. Top",
                            "target_uuid": "3fa85f64-5717-4562-b3fc-2c963f66af10",
                        },
                    ],
                    "wellbore": [],
                },
            },
        },
    },
    **inline_add_response(
        400,
        "Invalid mapping data or unsupported mapping type",
        [
            {"detail": "Mapping type '{mapping_type}' is not yet supported"},
        ],
    ),
    **inline_add_response(
        422,
        dedent(
            """
            Mappings resource contains invalid content or corrupted JSON.
            """
        ),
        [
            {"detail": "Invalid mappings in existing file: {error_message}"},
            {
                "detail": (
                    "Mappings could not be loaded because the project contains "
                    "invalid saved mappings."
                )
            },
        ],
    ),
}

# The PUT route reads raw JSON, so OpenAPI needs this schema for the GUI's
# autogenerated TypeScript body type.
PutMappingsOpenApiExtra: Final = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "anyOf": [
                        {"$ref": "#/components/schemas/InternalStratigraphyMappings"},
                        {"$ref": "#/components/schemas/InternalWellboreMappings"},
                    ]
                }
            }
        },
    }
}

CacheResponses: Final[Responses] = {
    **inline_add_response(
        404,
        "Cache revision not found for the specified resource",
        [{"detail": "Cache revision {revision_id} not found for resource {resource}"}],
    ),
    **inline_add_response(
        422,
        "Cache revision failed validation or not supported for the specified resource",
        [
            {
                "detail": "Resource {relative_path} is not supported "
                "for cache operations"
            },
            {"detail": "Invalid cached content for {resource}: {error}"},
        ],
    ),
}

ChangelogResponses: Final[Responses] = {
    **inline_add_response(
        404,
        "Changelog file not found",
        [{"detail": "No changelog file found at {path}"}],
    ),
    **inline_add_response(
        422,
        "Invalid changelog data or query parameters",
        [
            {"detail": "Invalid changelog format or data at {path}: {error}"},
            {"detail": "Invalid or corrupt JSON at {path}: {error}"},
            {
                "detail": (
                    "Generic changelog filter requires all of: field_name, "
                    "filter_value, filter_type, operator."
                )
            },
            {
                "detail": [
                    {
                        "type": "greater_than_equal",
                        "loc": ["query", "max_entries"],
                        "msg": "Input should be greater than or equal to 1",
                        "input": "0",
                        "ctx": {"ge": 1},
                    }
                ]
            },
        ],
    ),
}

SumoAssetsResponses: Final[Responses] = {
    **inline_add_response(
        404,
        "Sumo assets file not found",
        [{"detail": "Sumo assets file not found: {error}"}],
    ),
    **inline_add_response(
        422,
        "Invalid file content in Sumo assets file",
        [
            {"detail": "Sumo assets file contains invalid assets: {errors}"},
            {"detail": "Sumo assets file is not a valid JSON: {error}"},
        ],
    ),
}


@router.get(
    "/",
    response_model=FMUProject,
    summary="Returns the paths and configuration of the nearest project .fmu directory",
    description=dedent(
        """
        If a project is not already attached to the session id it will be
        attached after a call to this route. If one is already attached this
        route will return data for the project .fmu directory again.
        """
    ),
    responses={
        **GetSessionResponses,
        **ProjectResponses,
    },
)
async def get_project(session_service: SessionServiceDep) -> FMUProject:
    """Returns the paths and configuration of the nearest project .fmu directory.

    This directory is searched for above the current working directory.

    If the session contains a project .fmu directory already details of that project
    are returned.
    """
    try:
        fmu_dir = await session_service.get_or_attach_nearest_project()
    except SessionNotFoundError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail="Permission denied locating .fmu",
        ) from e
    except FileNotFoundError as e:
        path = Path.cwd()
        raise HTTPException(
            status_code=404, detail=f"No .fmu directory found from {path}"
        ) from e

    return _create_opened_project_response(fmu_dir)


@router.get(
    "/sumo_assets",
    response_model=list[SumoAsset],
    summary="Returns a list of Sumo assets.",
    description=dedent(
        """
        Returns a list of the assets that have been onboarded to
        the Sumo platform.
        """
    ),
    responses={**GetSessionResponses, **SumoAssetsResponses},
)
async def get_sumo_assets(project_service: ProjectServiceDep) -> list[SumoAsset]:
    """Returns a list of the Sumo assets."""
    try:
        return project_service.get_sumo_assets()
    except ValidationError as e:
        errors = [error.get("msg", str(error)) for error in e.errors()]
        raise HTTPException(
            status_code=422,
            detail=f"Sumo assets file contains invalid assets: {'; '.join(errors)}",
        ) from e
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=422, detail=f"Sumo assets file is not a valid JSON: {str(e)}"
        ) from e
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404, detail=f"Sumo assets file not found: {str(e)}"
        ) from e


@router.get(
    "/global_config_status",
    response_model=Ok,
    summary="Checks if a valid global config exists at the default location.",
    description=dedent(
        """
        Checks the global config at the default project location. If the global config
        does not validate, or is not found, a failed status code is returned.
        """
    ),
    responses={**GetSessionResponses, **GlobalConfigResponses},
)
async def get_global_config_status(project_service: ProjectServiceDep) -> Ok:
    """Checks if a valid global config exists at the default project location."""
    try:
        project_service.check_valid_global_config()
        return Ok()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except InvalidGlobalConfigurationError as e:
        raise HTTPException(
            status_code=422,
            detail=ConfigurationErrorDetail(
                message="The global config contains invalid or disallowed content.",
                error=str(e),
            ).model_dump(),
        ) from e
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=ValidationErrorDetail(
                message="The global config file is not valid.",
                validation_errors=e.errors(),
            ).model_dump(),
        ) from e


@router.post(
    "/",
    response_model=FMUProject,
    summary=(
        "Returns the path and configuration of the project .fmu directory at 'path'"
    ),
    description=dedent(
        """
        Used for when a user selects a project .fmu directory in a directory not
        found above the user's current working directory. Will overwrite the
        project .fmu directory attached to a session if one exists. If not, it is
        added to the session.
        """
    ),
    responses={
        **GetSessionResponses,
        **ProjectResponses,
        **ProjectExistsResponses,
    },
)
async def post_project(
    session_service: SessionServiceDep, fmu_dir_path: FMUDirPath
) -> FMUProject:
    """Returns the paths and configuration for the project .fmu directory at 'path'."""
    path = fmu_dir_path.path
    try:
        fmu_dir = await session_service.attach_project(path)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied accessing .fmu at {path}",
        ) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except FileExistsError as e:
        raise HTTPException(
            status_code=409, detail=f".fmu exists at {path} but is not a directory"
        ) from e

    return _create_opened_project_response(fmu_dir)


@router.post(
    "/init",
    response_model=FMUProject,
    summary=(
        "Initializes a project .fmu directory at 'path' and returns its paths and "
        "configuration"
    ),
    description=dedent(
        """
        If a project .fmu directory is already attached to the session, this will
       switch to use the newly created .fmu directory.
       """
    ),
    responses={
        **GetSessionResponses,
        **ProjectInitResponses,
    },
)
async def post_init_project(
    session_service: SessionServiceDep,
    fmu_dir_path: FMUDirPath,
) -> FMUProject:
    """Initializes .fmu at 'path' and returns its paths and configuration."""
    path = fmu_dir_path.path
    try:
        fmu_dir = await session_service.initialize_project(path)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied creating .fmu at {path}",
        ) from e
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404, detail=f"Path {path} does not exist"
        ) from e
    except InvalidFMUProjectPathError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except FileExistsError as e:
        raise HTTPException(
            status_code=409, detail=f".fmu already exists at {path}"
        ) from e

    return _create_opened_project_response(fmu_dir)


@router.post(
    "/global_config",
    response_model=Message,
    dependencies=[WritePermissionDep, RefreshLockDep],
    summary="Loads the global config into the project masterdata.",
    description=dedent(
        """
        Loads the global config into the project masterdata. If the global config does
        not validate, or is not found, a failed status code is returned. The endpoint
        takes an optional parameter, `path` as input: This should be given as a relative
        path, relative to the project root. If provided, the global config is searched
        for at this path. If not, the default project path will be used.
       """
    ),
    responses={
        **GetSessionResponses,
        **GlobalConfigResponses,
        **LockConflictResponses,
    },
)
async def post_global_config(
    project_service: ProjectServiceDep,
    path: GlobalConfigPath | None = None,
) -> Message:
    """Loads the global config into the .fmu config."""
    try:
        project_service.import_global_config(path)
        return Message(
            message="Global config masterdata was successfully loaded "
            "into the project masterdata."
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except FileExistsError as e:
        raise HTTPException(
            status_code=409,
            detail="A config file with masterdata already exists in "
            f".fmu at {project_service.config_path}.",
        ) from e
    except InvalidGlobalConfigurationError as e:
        raise HTTPException(
            status_code=422,
            detail=ConfigurationErrorDetail(
                message="The global config contains invalid or disallowed content.",
                error=str(e),
            ).model_dump(),
        ) from e
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=ValidationErrorDetail(
                message="The global config file is not valid.",
                validation_errors=e.errors(),
            ).model_dump(),
        ) from e


@router.delete(
    "/",
    response_model=Message,
    summary="Removes a project .fmu directory from a session",
    description=dedent(
        """
        This route simply removes (closes) a project .fmu directory from a session.
        This has no other side effects on the session.
        """
    ),
    responses={
        **GetSessionResponses,
    },
)
async def delete_project_session(
    session_service: ProjectSessionServiceDep,
) -> Message:
    """Deletes a project .fmu session if it exists."""
    try:
        await session_service.close_project()
        return Message(message="Project closed successfully")
    except SessionNotFoundError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


@router.post(
    "/lock_acquire",
    response_model=Message,
    summary="Attempts to acquire the project lock for editing",
    description=dedent(
        """
        Tries to upgrade the project session from read-only to editable by acquiring
        the project lock. If the lock cannot be acquired the project remains read-only
        and the last lock acquire error is recorded in the session.
        """
    ),
    responses={
        **GetSessionResponses,
    },
)
async def post_lock_acquire(session_service: ProjectSessionServiceDep) -> Message:
    """Attempts to acquire the project lock and returns a status message."""
    try:
        lock_acquired = await session_service.acquire_project_lock()
        if lock_acquired:
            message = "Project lock acquired."
        else:
            message = (
                "Project remains read-only because the lock could not be acquired. "
                "Check lock status for details."
            )
        return Message(message=message)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


@router.post(
    "/lock_release",
    response_model=Message,
    summary="Attempts to release the project lock",
    description=dedent(
        """
        Tries to release the project lock for the current session.
        If the lock is not currently held, the route returns an informational message.
        """
    ),
    responses={
        **GetSessionResponses,
    },
)
async def post_lock_release(session_service: ProjectSessionServiceDep) -> Message:
    """Attempts to release the project lock and returns a status message."""
    try:
        lock_released = await session_service.release_project_lock()
        if lock_released:
            message = "Project lock released."
        else:
            lock_status = session_service.get_lock_status()
            if lock_status.last_lock_release_error:
                message = (
                    f"Lock release attempted but an error occurred: "
                    f"{lock_status.last_lock_release_error}"
                )
            else:
                message = (
                    "Lock was not released because the lock is not currently held."
                )
        return Message(message=message)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


@router.post(
    "/lock_refresh",
    response_model=Message,
    dependencies=[RefreshLockDep],
    summary="Refreshes the project lock timeout",
    description=dedent(
        """
        Explicitly refreshes the project lock timeout if the current session
        holds the lock. This should be called when the user actively indicates they
        want to continue editing (e.g., pressing an 'Edit' button in the GUI).

        Returns a message indicating whether the lock was successfully refreshed.
        """
    ),
    responses={
        **GetSessionResponses,
    },
)
async def post_lock_refresh(
    session_service: ProjectSessionServiceDep,
) -> Message:
    """Refreshes the project lock and returns a status message."""
    lock_status = session_service.get_lock_status()
    if lock_status.is_lock_acquired and lock_status.last_lock_refresh_error is None:
        message = "Project lock refreshed successfully."
    elif lock_status.last_lock_refresh_error:
        message = (
            f"Lock refresh attempted but an error occurred: "
            f"{lock_status.last_lock_refresh_error}"
        )
    else:
        message = "Lock was not refreshed because the lock is not currently held."
    return Message(message=message)


@router.get(
    "/lock_status",
    response_model=LockStatus,
    summary="Returns the lock status and lock file contents",
    description=dedent(
        """
        Returns information about the project lock including whether the current
        session holds the lock and the contents of the lock file if it exists.
        This is useful for debugging lock conflicts and showing users who has
        the project locked.
        """
    ),
    responses={
        **GetSessionResponses,
        **ProjectResponses,
    },
)
async def get_lock_status(
    session_service: ProjectSessionServiceDep,
) -> LockStatus:
    """Returns the lock status and lock file contents if available."""
    return session_service.get_lock_status()


@router.patch(
    "/masterdata",
    response_model=Message,
    dependencies=[WritePermissionDep, RefreshLockDep],
    summary="Saves SMDA masterdata to the project .fmu directory",
    description=dedent(
        """
        Saves masterdata from SMDA to the project .fmu directory.
        If existing masterdata is present, it will be updated with the new masterdata.
       """
    ),
    responses={
        **GetSessionResponses,
        **ProjectResponses,
        **LockConflictResponses,
    },
)
async def patch_masterdata(
    project_service: ProjectServiceDep,
    smda_masterdata: Smda,
) -> Message:
    """Saves SMDA masterdata to the project .fmu directory."""
    project_service.update_masterdata(smda_masterdata)
    return Message(message="Saved SMDA masterdata")


@router.patch(
    "/model",
    response_model=Message,
    dependencies=[WritePermissionDep, RefreshLockDep],
    summary="Saves model data to the project .fmu directory",
    description=dedent(
        """
        Saves model data to the project .fmu directory.
        If existing model data is present, it will be replaced by the new
        model data.
       """
    ),
    responses={
        **GetSessionResponses,
        **ProjectResponses,
        **LockConflictResponses,
    },
)
async def patch_model(project_service: ProjectServiceDep, model: Model) -> Message:
    """Saves model data to the project .fmu directory."""
    project_service.update_model(model)
    return Message(message="Saved model data")


@router.patch(
    "/access",
    response_model=Message,
    dependencies=[WritePermissionDep, RefreshLockDep],
    summary="Saves access data to the project .fmu directory",
    description=dedent(
        """
        Saves access data to the project .fmu directory.
        If existing access data is present, it will be replaced by the new
        access data.
       """
    ),
    responses={
        **GetSessionResponses,
        **ProjectResponses,
        **LockConflictResponses,
    },
)
async def patch_access(project_service: ProjectServiceDep, access: Access) -> Message:
    """Saves access data to the project .fmu directory."""
    project_service.update_access(access)
    return Message(message="Saved access data")


@router.patch(
    "/cache_max_revisions",
    response_model=Message,
    dependencies=[WritePermissionDep, RefreshLockDep],
    summary="Saves cache max revisions to the project .fmu directory",
    description=dedent(
        """
        Saves the maximum number of cache revisions to keep per resource in the
        project .fmu configuration.
        """
    ),
    responses={
        **GetSessionResponses,
        **ProjectResponses,
        **LockConflictResponses,
    },
)
async def patch_cache_max_revisions(
    project_service: ProjectServiceDep,
    cache_max_revisions: CacheRetention,
) -> Message:
    """Saves cache max revisions to the project .fmu directory."""
    project_service.update_cache_max_revisions(cache_max_revisions)
    return Message(message="Saved cache max revisions")


@router.get(
    "/rms_projects",
    response_model=RmsProjectPathsResult,
    summary="Gets the paths of RMS projects in this project directory",
    description=dedent(
        """
        Returns a list of paths to RMS projects found in the current project directory.
        """
    ),
    responses={
        **GetSessionResponses,
        **ProjectResponses,
    },
)
async def get_rms_projects(
    project_service: ProjectServiceDep,
) -> RmsProjectPathsResult:
    """Get the paths of RMS projects in this project directory."""
    try:
        rms_project_paths = project_service.get_rms_projects()
        return RmsProjectPathsResult(
            results=[RmsProjectPath(path=path) for path in rms_project_paths]
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail="Permission denied while scanning for RMS projects.",
        ) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch(
    "/rms",
    response_model=Message,
    dependencies=[WritePermissionDep, RefreshLockDep],
    summary="Saves the RMS project path and version in the project .fmu directory",
    description=dedent(
        """
        Saves the RMS project path and version to the project .fmu directory.
        The RMS version is set automatically based on the provided RMS project path.
        If existing RMS project path and version are present, they will be
        replaced by the new RMS project path and version.
       """
    ),
    responses={
        **GetSessionResponses,
        **ProjectResponses,
        **LockConflictResponses,
        **inline_add_response(
            400,
            "The RMS version in the project is not supported",
            [{"detail": "RMS version error for project at '{path}': {error}"}],
        ),
    },
)
async def patch_rms(
    project_service: ProjectServiceDep,
    rms_project_path: RmsProjectPath,
) -> Message:
    """Saves the RMS project path and version in the project .fmu directory."""
    try:
        rms_version = project_service.update_rms(rms_project_path.path)
        return Message(message=f"Saved RMS project path with RMS version {rms_version}")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RmsVersionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.patch(
    "/rms/coordinate_system",
    response_model=Message,
    dependencies=[WritePermissionDep, RefreshLockDep],
    summary="Saves the RMS coordinate system in the project .fmu directory",
    description=dedent(
        """
        Saves the RMS coordinate system to the project .fmu directory.
        Requires that the RMS project path has been set first via PATCH /project/rms.
        If an existing coordinate system is present, it will be replaced.
        """
    ),
    responses={
        **GetSessionResponses,
        **ProjectResponses,
        **LockConflictResponses,
        **RmsConfigNotSetResponses,
    },
)
async def patch_rms_coordinate_system(
    project_service: ProjectServiceDep,
    coordinate_system: RmsCoordinateSystem,
) -> Message:
    """Saves the RMS coordinate system in the project .fmu directory."""
    try:
        project_service.update_rms_coordinate_system(coordinate_system)
        return Message(message="Saved RMS coordinate system")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.patch(
    "/rms/stratigraphic_framework",
    response_model=Message,
    dependencies=[WritePermissionDep, RefreshLockDep],
    summary="Saves the RMS stratigraphic framework in the project .fmu directory",
    description=dedent(
        """
        Saves the RMS stratigraphic framework (zones and horizons) to the project
        .fmu directory. Requires that the RMS project path has been set first via
        PATCH /project/rms. If existing zones or horizons are present, they will
        be replaced.
        """
    ),
    responses={
        **GetSessionResponses,
        **ProjectResponses,
        **LockConflictResponses,
        **RmsConfigNotSetResponses,
        **RmsStratigraphicFrameworkResponses,
    },
)
async def patch_rms_stratigraphic_framework(
    project_service: ProjectServiceDep,
    stratigraphic_framework: RmsStratigraphicFramework,
) -> Message:
    """Saves the RMS stratigraphic framework in the project .fmu directory."""
    try:
        project_service.update_rms_stratigraphic_framework(
            stratigraphic_framework.zones, stratigraphic_framework.horizons
        )
        return Message(message="Saved RMS stratigraphic framework")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.patch(
    "/rms/wells",
    response_model=Message,
    dependencies=[WritePermissionDep, RefreshLockDep],
    summary="Saves the RMS wells in the project .fmu directory",
    description=dedent(
        """
        Saves the RMS wells to the project .fmu directory.
        Requires that the RMS project path has been set first via PATCH /project/rms.
        If existing wells are present, they will be replaced.
        """
    ),
    responses={
        **GetSessionResponses,
        **ProjectResponses,
        **LockConflictResponses,
        **RmsConfigNotSetResponses,
    },
)
async def patch_rms_wells(
    project_service: ProjectServiceDep,
    wells: list[RmsWell],
) -> Message:
    """Saves the RMS wells in the project .fmu directory."""
    try:
        project_service.update_rms_wells(wells)
        return Message(message="Saved RMS wells")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get(
    "/cache",
    response_model=CacheList,
    summary="List cache revisions",
    description=dedent(
        """
        Returns a list of revision filenames for the resource specified by the
        `resource` query parameter. The filenames are used with
        GET /cache/{revision_id}.
        """
    ),
    responses={**GetSessionResponses, **ProjectResponses},
)
async def get_cache(
    resource_service: ResourceServiceDep,
    resource: CacheResource,
) -> CacheList:
    """List all cache revisions for a specific resource."""
    try:
        return resource_service.list_cache_revisions(resource)
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Permission denied accessing .fmu at {resource_service.fmu_dir_path}"
            ),
        ) from e


@router.get(
    "/cache/{revision_id}",
    response_model=CacheContent,
    summary="Get cache revision content",
    description=dedent(
        """
        Retrieve the content of a specific cache revision.

        The revision_id should be a filename from the list returned by GET /cache
        (e.g., 20260112T143045.123456Z-a1b2c3d4.json).

        The `resource` query parameter selects which resource cache to read.

        Returns the parsed JSON content from the cached file in the `data` field.
        """
    ),
    responses={**GetSessionResponses, **ProjectResponses, **CacheResponses},
)
async def get_cache_revision(
    resource_service: ResourceServiceDep,
    revision_id: str,
    resource: CacheResource,
) -> CacheContent:
    """Get the content of a specific cache revision."""
    try:
        return resource_service.get_cache_content(resource, revision_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Permission denied accessing .fmu at {resource_service.fmu_dir_path}"
            ),
        ) from e


@router.get(
    "/cache/diff/{revision_id}",
    response_model=list[ResourceDiff],
    summary="Get diff between current resource and cache revision",
    description=dedent(
        """
        Compare a resource file in the current project with a cached revision.

        The `resource` query parameter selects which resource to diff.
        The response is a list of changes keyed by `field_path`.
        """
    ),
    responses={**GetSessionResponses, **ProjectResponses, **CacheResponses},
)
async def get_cache_diff(
    resource_service: ResourceServiceDep,
    revision_id: str,
    resource: CacheResource,
) -> list[ResourceDiff]:
    """Get the diff between the current resource and a cache revision."""
    try:
        return resource_service.get_cache_diff(resource, revision_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Permission denied accessing .fmu at {resource_service.fmu_dir_path}"
            ),
        ) from e


@router.post(
    "/cache/restore/{revision_id}",
    response_model=Message,
    dependencies=[WritePermissionDep, RefreshLockDep],
    summary="Restore a resource from a cache revision",
    description=dedent(
        """
        Restore a resource from a cache revision (overwrites current resource).

        The current resource state is cached before overwriting (when present).

        The `resource` query parameter selects which resource to restore.

        **Example flow:**

        1. Current resource is in state A
        2. Call restore with a revision from state B
        3. Your current state A is cached (when present)
        4. Resource is now in state B
        5. To undo: restore from the newly created cache entry (your state A backup)
        """
    ),
    responses={
        **GetSessionResponses,
        **ProjectResponses,
        **CacheResponses,
        **LockConflictResponses,
    },
)
async def post_cache_restore(
    resource_service: ResourceServiceDep,
    revision_id: str,
    resource: CacheResource,
) -> Message:
    """Restore a resource from a cache revision."""
    try:
        resource_service.restore_from_cache(resource, revision_id)
        return Message(message=f"Restored {resource.value} from revision {revision_id}")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Permission denied accessing .fmu at {resource_service.fmu_dir_path}"
            ),
        ) from e


@router.get(
    "/restore/check",
    response_model=RestorableFilesResponse,
    summary="Checks which missing project .fmu resources can be restored",
    description=dedent(
        """
        Lists recoverable missing project .fmu content from in-memory state.
        """
    ),
    responses={
        **GetSessionResponses,
        **ProjectResponses,
    },
)
async def get_restore_check(
    project_service: ProjectServiceForRestoreDep,
) -> RestorableFilesResponse:
    """List recoverable missing project .fmu files for the current session."""
    return RestorableFilesResponse(files=project_service.get_restorable_fmu_files())


@router.post(
    "/restore",
    response_model=RestorableFilesResponse,
    summary="Restores missing project .fmu resources for the current session",
    description=dedent(
        """
        Attempts to recover missing project .fmu content from in-memory state.
        """
    ),
    responses={
        **GetSessionResponses,
        **ProjectResponses,
        **LockConflictResponses,
    },
)
async def post_restore(
    project_service: ProjectServiceForRestoreDep,
) -> RestorableFilesResponse:
    """Attempt recovery of missing project .fmu files."""
    try:
        return RestorableFilesResponse(files=project_service.restore_fmu_files())
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except PermissionError as e:
        if "Cannot write to .fmu directory because it is locked by" in str(e):
            raise HTTPException(
                status_code=423,
                detail=f"Project lock conflict: {e}",
            ) from e
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied accessing .fmu at {project_service.config_path}",
        ) from e


@router.get(
    "/mappings/{mapping_type}/{source_system}",
    response_model=InternalMappings,
    summary="Returns internal mappings for a specific mapping type and source system.",
    description=dedent(
        """
        Retrieves internal mappings for the specified mapping_type and source_system
        from the project's .fmu directory.

        Example: GET /project/mappings/stratigraphy/rms returns the
        internal stratigraphy mappings whose source system is RMS.
        """
    ),
    responses={
        **GetSessionResponses,
        **ProjectResponses,
        **GetMappingsResponses,
    },
)
async def get_mappings(
    mappings_service: MappingsServiceDep,
    mapping_type: MappingType,
    source_system: DataSystem,
) -> InternalMappings:
    """Returns internal mappings for a specific mapping type and source system."""
    try:
        return mappings_service.get_internal_mappings_by_source_system(
            mapping_type,
            source_system,
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Permission denied accessing .fmu at {mappings_service.fmu_dir_path}"
            ),
        ) from e
    except ValidationError as e:
        errors = [error.get("msg", str(error)) for error in e.errors()]
        raise HTTPException(
            status_code=422,
            detail=f"Invalid mappings in existing file: {'; '.join(errors)}",
        ) from e
    except ValueError as e:
        if str(e).startswith(
            (
                "Invalid content in resource file for 'MappingsManager:",
                "Invalid JSON in resource file for 'MappingsManager':",
            )
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Mappings could not be loaded because the project contains "
                    "invalid saved mappings."
                ),
            ) from e
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.put(
    "/mappings/{mapping_type}/{source_system}",
    response_model=Message,
    dependencies=[WritePermissionDep, RefreshLockDep],
    summary="Updates internal mappings for a specific mapping type and source system",
    description=dedent(
        """
        Replaces internal mappings for the specified mapping_type and source system in
        the project's .fmu directory.

        The request body should contain the internal mappings collection for the
        specified source system.

        Example: PUT /project/mappings/stratigraphy/rms replaces the stored
        internal stratigraphy mappings whose source system is RMS.
        """
    ),
    responses={
        **GetSessionResponses,
        **ProjectResponses,
        **MappingsResponses,
        **LockConflictResponses,
    },
    openapi_extra=PutMappingsOpenApiExtra,
)
async def put_mappings(
    mappings_service: MappingsServiceDep,
    mapping_type: MappingType,
    source_system: DataSystem,
    mappings: Request,
) -> Message:
    """Updates internal mappings for a specific mapping type and source system.

    The mapping type is extracted from the URL and used to parse the body
    explicitly. This avoids ambiguous union validation when a payload, such as
    an empty list, is valid for both mapping types.
    """
    try:
        mappings_payload: object = await mappings.json()
        parsed_mappings = _parse_internal_mappings_payload(
            mapping_type, mappings_payload
        )
        mappings_service.update_internal_mappings_by_source_system(
            mapping_type, source_system, parsed_mappings
        )
        return Message(message=f"Saved {mapping_type.value} mappings")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail="Invalid mappings JSON") from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail="Permission denied while trying to update the mappings.",
        ) from e
    except ValidationError as e:
        errors = [error.get("msg", str(error)) for error in e.errors()]
        raise HTTPException(
            status_code=422,
            detail=f"Invalid mappings: {'; '.join(errors)}",
        ) from e
    except ValueError as e:
        if str(e).startswith(
            (
                "Invalid content in resource file for 'MappingsManager:",
                "Invalid JSON in resource file for 'MappingsManager':",
            )
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Mappings were not updated because the project contains "
                    "invalid saved mappings."
                ),
            ) from e
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get(
    "/changelog",
    response_model=Log[ChangeInfo],
    summary="Returns changelog for the project.",
    description=dedent(
        """
        Retrieves changelog from the project's .fmu directory.
        """
    ),
    responses={
        **GetSessionResponses,
        **ProjectResponses,
        **ChangelogResponses,
    },
)
async def get_changelog(
    changelog_service: ChangelogServiceDep,
    changelog_filters: ChangelogFiltersDep,
) -> Log[ChangeInfo]:
    """Returns changelog for the project."""
    try:
        return changelog_service.get_changelog(
            change_type=changelog_filters.change_type,
            filter_=changelog_filters.filter_,
            max_entries=changelog_filters.max_entries,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail="Permission denied accessing changelog at"
            f"{changelog_service.fmu_dir_path}.",
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail="Invalid changelog format or data.",
        ) from e


def _create_opened_project_response(fmu_dir: ProjectFMUDirectory) -> FMUProject:
    """Creates an FMUProject response model for an opened project.

    Includes path, configuration, and read-only status determined by lock acquisition.
    Raises HTTP exceptions for corrupt or inaccessible projects.
    """
    try:
        service = ProjectService(fmu_dir)
        return service.get_project_data()
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=f"Missing configuration file in project at {fmu_dir.path}: {e}",
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Corrupt project found at {fmu_dir.path}: {e}",
        ) from e
    except PermissionError as e:
        raise HTTPException(
            status_code=403, detail="Permission denied accessing .fmu"
        ) from e


def _parse_internal_mappings_payload(
    mapping_type: MappingType,
    payload: object,
) -> InternalStratigraphyMappings | InternalWellboreMappings:
    """Parse the request body as the given mapping type.

    Use the selected mapping type instead of letting a union guess from the body
    shape. A union would make validation depend on which mappings list Pydantic
    can match first.
    """
    if mapping_type == MappingType.stratigraphy:
        return TypeAdapter(InternalStratigraphyMappings).validate_python(payload)

    if mapping_type == MappingType.wellbore:
        return TypeAdapter(InternalWellboreMappings).validate_python(payload)

    raise ValueError(  # pragma: no cover
        f"Mapping type '{mapping_type}' is not yet supported"
    )
