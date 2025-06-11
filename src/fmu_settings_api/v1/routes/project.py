"""Routes to add an FMU project to an existing session."""

from pathlib import Path
from textwrap import dedent
from typing import Final

from fastapi import APIRouter, HTTPException, Response
from fmu.settings import find_nearest_fmu_directory, get_fmu_directory
from fmu.settings._init import init_fmu_directory

from fmu_settings_api.deps import (
    ProjectSessionDep,
    SessionDep,
)
from fmu_settings_api.models import FMUDirPath, FMUProject, Message
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
        return FMUProject(
            path=fmu_dir.base_path,
            project_dir_name=fmu_dir.base_path.name,
            config=fmu_dir.config.load(),
        )

    try:
        path = Path.cwd()
        fmu_dir = find_nearest_fmu_directory(path)
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
            detail="Permission denied locating .fmu",
        ) from e
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404, detail=f"No .fmu directory found from {path}"
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
    try:
        fmu_dir = get_fmu_directory(path)
        _ = await add_fmu_project_to_session(session.id, fmu_dir)
        return FMUProject(
            path=fmu_dir.base_path,
            project_dir_name=fmu_dir.base_path.name,
            config=fmu_dir.config.load(),
        )
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
