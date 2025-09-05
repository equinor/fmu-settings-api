"""Routes to add an FMU project to an existing session."""

from pathlib import Path
from textwrap import dedent
from typing import Final

from fastapi import APIRouter, HTTPException, Response
from fmu.config import utilities  # type: ignore
from fmu.datamodels.fmu_results import global_configuration
from fmu.datamodels.fmu_results.fields import Smda
from fmu.settings import (
    ProjectFMUDirectory,
    find_nearest_fmu_directory,
    get_fmu_directory,
)
from fmu.settings._init import init_fmu_directory
from pydantic import ValidationError

from fmu_settings_api.deps import (
    ProjectSessionDep,
    SessionDep,
)
from fmu_settings_api.models import FMUDirPath, FMUProject, Message
from fmu_settings_api.models.project import GlobalConfigPath
from fmu_settings_api.session import (
    ProjectSession,
    SessionNotFoundError,
    add_fmu_project_to_session,
    remove_fmu_project_from_session,
)
from fmu_settings_api.v1.responses import (
    GetSessionResponses,
    Responses,
    inline_add_response,
)

GLOBAL_CONFIG_DEFAULT_PATH: Final[Path] = Path("fmuconfig/output/global_variables.yml")
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
            {
                "detail": "The global config file is not valid "
                "at path {global_config_path}"
            },
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
        return _get_project_details(fmu_dir)

    try:
        path = Path.cwd()
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

    return _get_project_details(fmu_dir)


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

    return _get_project_details(fmu_dir)


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
        return FMUProject(
            path=fmu_dir.base_path,
            project_dir_name=fmu_dir.base_path.name,
            config=fmu_dir.config.load(),
        )
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
    responses={**GetSessionResponses, **GlobalConfigResponses},
)
async def post_global_config(
    project_session: ProjectSessionDep, path: GlobalConfigPath | None = None
) -> Message:
    """Loads the global config into the .fmu config."""
    try:
        fmu_dir = project_session.project_fmu_directory
        relative_path = GLOBAL_CONFIG_DEFAULT_PATH
        if path is not None:
            relative_path = path.relative_path

        project_root = fmu_dir.path.parent
        global_config_path = project_root / relative_path
        if not global_config_path.exists():
            raise FileNotFoundError(f"No file exists at path {global_config_path}.")

        if fmu_dir.config.load().masterdata is not None:
            raise FileExistsError("Masterdata exists in the project config.")

        global_config_dict = utilities.yaml_load(global_config_path)
        global_config = global_configuration.GlobalConfiguration.model_validate(
            global_config_dict
        )

        fmu_dir.set_config_value("masterdata", global_config.masterdata.model_dump())

        return Message(
            message=(
                f"Global config masterdata at {global_config_path} was "
                "successfully loaded into the project masterdata."
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
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "The global config file is not valid at path "
                f"{global_config_path}.",
                "validation_error": str(e),
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
async def delete_project_session(
    session: ProjectSessionDep, response: Response
) -> Message:
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


@router.patch(
    "/masterdata",
    response_model=Message,
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
    },
)
async def patch_masterdata(
    project_session: ProjectSessionDep, smda_masterdata: Smda
) -> Message:
    """Saves SMDA masterdata to the project .fmu directory."""
    fmu_dir = project_session.project_fmu_directory
    try:
        fmu_dir.set_config_value("masterdata.smda", smda_masterdata.model_dump())
        return Message(message=f"Saved SMDA masterdata to {fmu_dir.path}")
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied updating .fmu at {fmu_dir.path}",
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


def _get_project_details(fmu_dir: ProjectFMUDirectory) -> FMUProject:
    """Returns the paths and configuration of a project FMU directory."""
    try:
        return FMUProject(
            path=fmu_dir.base_path,
            project_dir_name=fmu_dir.base_path.name,
            config=fmu_dir.config.load(),
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
