"""Routes to add an FMU project to an existing session."""

from pathlib import Path
from textwrap import dedent
from typing import Final

from fastapi import APIRouter, HTTPException
from fmu.datamodels.fmu_results.fields import Access, Model, Smda
from fmu.settings import (
    ProjectFMUDirectory,
    find_nearest_fmu_directory,
    get_fmu_directory,
)
from fmu.settings._global_config import (
    InvalidGlobalConfigurationError,
    find_global_config,
)
from fmu.settings._init import init_fmu_directory
from pydantic import ValidationError

from fmu_settings_api.deps import (
    ProjectSessionDep,
    SessionDep,
    WritePermissionDep,
)
from fmu_settings_api.models import FMUDirPath, FMUProject, Message
from fmu_settings_api.models.common import Ok
from fmu_settings_api.models.project import GlobalConfigPath, LockStatus
from fmu_settings_api.services.user import remove_from_recent_projects
from fmu_settings_api.session import (
    ProjectSession,
    SessionNotFoundError,
    add_fmu_project_to_session,
    remove_fmu_project_from_session,
    try_acquire_project_lock,
)
from fmu_settings_api.v1.responses import (
    GetSessionResponses,
    Responses,
    inline_add_response,
)

router = APIRouter(prefix="/project", tags=["project"])

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
async def get_project(session: SessionDep) -> FMUProject:
    """Returns the paths and configuration of the nearest project .fmu directory.

    This directory is searched for above the current working directory.

    If the session contains a project .fmu directory already details of that project
    are returned.
    """
    if isinstance(session, ProjectSession):
        fmu_dir = session.project_fmu_directory
        return _create_opened_project_response(fmu_dir)

    path = Path.cwd()
    try:
        fmu_dir = find_nearest_fmu_directory(path)
        await add_fmu_project_to_session(session.id, fmu_dir)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail="Permission denied locating .fmu",
        ) from e
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404, detail=f"No .fmu directory found from {path}"
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return _create_opened_project_response(fmu_dir)


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
async def get_global_config_status(project_session: ProjectSessionDep) -> Ok:
    """Checks if a valid global config exists at the default project location."""
    project_root = project_session.project_fmu_directory.path.parent

    try:
        existing_config = find_global_config(project_root)
        if existing_config is None:
            raise FileNotFoundError("No valid global config file found in the project.")
        return Ok()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except InvalidGlobalConfigurationError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "The global config contains invalid or disallowed content.",
                "error": str(e),
            },
        ) from e
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "The global config file is not valid.",
                "validation_errors": e.errors(),
            },
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


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
async def post_project(session: SessionDep, fmu_dir_path: FMUDirPath) -> FMUProject:
    """Returns the paths and configuration for the project .fmu directory at 'path'."""
    path = fmu_dir_path.path
    if not path.exists():
        remove_from_recent_projects(path, session.user_fmu_directory)
        raise HTTPException(status_code=404, detail=f"Path {path} does not exist")

    try:
        fmu_dir = get_fmu_directory(path)
        await add_fmu_project_to_session(session.id, fmu_dir)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied accessing .fmu at {path}",
        ) from e
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404, detail=f"No .fmu directory found at {path}"
        ) from e
    except FileExistsError as e:
        raise HTTPException(
            status_code=409, detail=f".fmu exists at {path} but is not a directory"
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

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
        **ProjectResponses,
        **ProjectExistsResponses,
    },
)
async def init_project(
    session: SessionDep,
    fmu_dir_path: FMUDirPath,
) -> FMUProject:
    """Initializes .fmu at 'path' and returns its paths and configuration."""
    path = fmu_dir_path.path
    try:
        fmu_dir = init_fmu_directory(path)
        _ = await add_fmu_project_to_session(session.id, fmu_dir)
        return _create_opened_project_response(fmu_dir)
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
    except FileExistsError as e:
        raise HTTPException(
            status_code=409, detail=f".fmu already exists at {path}"
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/global_config",
    response_model=Message,
    dependencies=[WritePermissionDep],
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
    project_session: ProjectSessionDep,
    path: GlobalConfigPath | None = None,
) -> Message:
    """Loads the global config into the .fmu config."""
    fmu_dir = project_session.project_fmu_directory
    project_root = fmu_dir.path.parent

    try:
        if fmu_dir.config.load().masterdata is not None:
            raise FileExistsError("Masterdata exists in the project config.")

        extra_output_paths = None
        if path is not None:
            global_config_path = project_root / path.relative_path
            extra_output_paths = [global_config_path]

        global_config = find_global_config(
            project_root, extra_output_paths=extra_output_paths
        )
        if global_config is None:
            raise FileNotFoundError("No valid global config file found in the project.")

        fmu_dir.set_config_value("masterdata", global_config.masterdata.model_dump())

        return Message(
            message=(
                "Global config masterdata was successfully loaded "
                "into the project masterdata."
            ),
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except FileExistsError as e:
        raise HTTPException(
            status_code=409,
            detail="A config file with masterdata already exists in "
            f".fmu at {fmu_dir.config.path}.",
        ) from e
    except InvalidGlobalConfigurationError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "The global config contains invalid or disallowed content.",
                "error": str(e),
            },
        ) from e
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "The global config file is not valid.",
                "validation_errors": e.errors(),
            },
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


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
async def delete_project_session(session: ProjectSessionDep) -> Message:
    """Deletes a project .fmu session if it exists."""
    try:
        await remove_fmu_project_from_session(session.id)
        return Message(
            message=(
                f"FMU directory {session.project_fmu_directory.path} closed "
                "successfully"
            ),
        )
    except SessionNotFoundError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


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
async def post_lock_acquire(project_session: ProjectSessionDep) -> Message:
    """Attempts to acquire the project lock and returns a status message."""
    try:
        updated_session = await try_acquire_project_lock(project_session.id)
        lock = updated_session.project_fmu_directory._lock
        if lock.is_acquired():
            return Message(message="Project lock acquired.")
    except SessionNotFoundError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return Message(
        message="Project remains read-only because the lock could not be acquired."
        "Check lock status for details."
    )


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
async def get_lock_status(project_session: ProjectSessionDep) -> LockStatus:
    """Returns the lock status and lock file contents if available."""
    fmu_dir = project_session.project_fmu_directory

    is_lock_acquired = False
    lock_file_exists = False
    lock_info = None
    lock_status_error = None
    lock_file_read_error = None

    try:
        is_lock_acquired = fmu_dir._lock.is_acquired()
    except Exception as e:
        lock_status_error = f"Failed to check lock status: {str(e)}"

    try:
        if fmu_dir._lock.exists:
            lock_file_exists = True
            try:
                lock_info = fmu_dir._lock.load(force=True, store_cache=False)
            except (OSError, PermissionError) as e:
                lock_file_read_error = f"Failed to read lock file: {str(e)}"
            except ValueError as e:
                lock_file_read_error = f"Failed to parse lock file: {str(e)}"
            except Exception as e:
                lock_file_read_error = f"Failed to process lock file: {str(e)}"
        else:
            lock_file_exists = False
    except Exception as e:
        lock_file_read_error = f"Failed to access lock file path: {str(e)}"

    return LockStatus(
        is_lock_acquired=is_lock_acquired,
        lock_file_exists=lock_file_exists,
        lock_info=lock_info,
        lock_status_error=lock_status_error,
        lock_file_read_error=lock_file_read_error,
        last_lock_acquire_error=project_session.lock_errors.acquire,
        last_lock_release_error=project_session.lock_errors.release,
        last_lock_refresh_error=project_session.lock_errors.refresh,
    )


@router.patch(
    "/masterdata",
    response_model=Message,
    dependencies=[WritePermissionDep],
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
        **ProjectExistsResponses,
        **LockConflictResponses,
    },
)
async def patch_masterdata(
    project_session: ProjectSessionDep,
    smda_masterdata: Smda,
) -> Message:
    """Saves SMDA masterdata to the project .fmu directory."""
    fmu_dir = project_session.project_fmu_directory
    try:
        fmu_dir.set_config_value("masterdata.smda", smda_masterdata.model_dump())
        return Message(message=f"Saved SMDA masterdata to {fmu_dir.path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch(
    "/model",
    response_model=Message,
    dependencies=[WritePermissionDep],
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
        **ProjectExistsResponses,
        **LockConflictResponses,
    },
)
async def patch_model(project_session: ProjectSessionDep, model: Model) -> Message:
    """Saves model data to the project .fmu directory."""
    fmu_dir = project_session.project_fmu_directory
    try:
        fmu_dir.set_config_value("model", model.model_dump())
        return Message(message=f"Saved model data to {fmu_dir.path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch(
    "/access",
    response_model=Message,
    dependencies=[WritePermissionDep],
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
        **ProjectExistsResponses,
        **LockConflictResponses,
    },
)
async def patch_access(project_session: ProjectSessionDep, access: Access) -> Message:
    """Saves access data to the project .fmu directory."""
    fmu_dir = project_session.project_fmu_directory
    try:
        fmu_dir.set_config_value("access", access.model_dump())
        return Message(message=f"Saved access data to {fmu_dir.path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


def _create_opened_project_response(fmu_dir: ProjectFMUDirectory) -> FMUProject:
    """Creates an FMUProject response model for an opened project.

    Includes path, configuration, and read-only status determined by lock acquisition.
    Raises HTTP exceptions for corrupt or inaccessible projects.
    """
    try:
        is_read_only = not fmu_dir._lock.is_acquired()

        return FMUProject(
            path=fmu_dir.base_path,
            project_dir_name=fmu_dir.base_path.name,
            config=fmu_dir.config.load(),
            is_read_only=is_read_only,
        )
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(
            status_code=500,
            detail=f"Corrupt project found at {fmu_dir.path}: {e}",
        ) from e
    except PermissionError as e:
        raise HTTPException(
            status_code=403, detail="Permission denied accessing .fmu"
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
