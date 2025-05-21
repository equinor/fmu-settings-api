"""Routes to add an FMU project to an existing session."""

from pathlib import Path

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

router = APIRouter(prefix="/project", tags=["project"])


@router.get("/", response_model=FMUProject)
async def get_project(session: SessionDep) -> FMUProject:
    """Returns the paths and configuration for the nearest project .fmu directory.

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


@router.post("/", response_model=FMUProject)
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


@router.delete("/", response_model=Message)
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


@router.post("/init", response_model=FMUProject)
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
