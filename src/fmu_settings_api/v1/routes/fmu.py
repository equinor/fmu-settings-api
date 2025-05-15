"""Routes to initialize a .fmu session."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from fmu.settings import find_nearest_fmu_directory, get_fmu_directory
from fmu.settings._init import init_fmu_directory

from fmu_settings_api.config import settings
from fmu_settings_api.deps import SessionDep
from fmu_settings_api.models import FMUDirPath, FMUProject, Message
from fmu_settings_api.session import create_fmu_session, destroy_fmu_session

router = APIRouter(prefix="/fmu", tags=["fmu"])


@router.get("/", response_model=FMUProject)
async def get_cwd_fmu_directory_session(response: Response) -> FMUProject:
    """Returns the paths and configuration for the nearest .fmu directory.

    This directory is searched for above the current working directory.
    """
    try:
        path = Path.cwd()
        fmu_dir = find_nearest_fmu_directory(path)
        session_id = await create_fmu_session(fmu_dir)
        response.set_cookie(
            key=settings.SESSION_COOKIE_KEY,
            value=session_id,
            httponly=True,
            secure=True,
            samesite="lax",
        )
        return FMUProject(
            path=fmu_dir.base_path,
            project_dir_name=fmu_dir.base_path.name,
            config=fmu_dir.config.load(),
        )
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
async def get_fmu_directory_session(
    response: Response, fmu_dir_path: FMUDirPath
) -> FMUProject:
    """Returns the paths and configuration for the .fmu directory at 'path'."""
    path = fmu_dir_path.path
    try:
        fmu_dir = get_fmu_directory(path)
        session_id = await create_fmu_session(fmu_dir)
        response.set_cookie(
            key=settings.SESSION_COOKIE_KEY,
            value=session_id,
            httponly=True,
            secure=False,
            samesite="lax",
        )
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
async def delete_fmu_directory_session(
    session: SessionDep, response: Response
) -> Message:
    """Deletes a .fmu session if it exists."""
    try:
        await destroy_fmu_session(session.id)
        response.delete_cookie(key=session.id)
        return Message(
            message=f"FMU directory {session.fmu_directory.path} closed successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/init", response_model=FMUProject)
async def init_fmu_directory_session(
    response: Response, fmu_dir_path: FMUDirPath
) -> FMUProject:
    """Initializes .fmu at 'path' and returns its paths and configuration."""
    path = fmu_dir_path.path
    try:
        fmu_dir = init_fmu_directory(path)
        session_id = await create_fmu_session(fmu_dir)
        response.set_cookie(
            key=settings.SESSION_COOKIE_KEY,
            value=session_id,
            httponly=True,
            secure=False,
            samesite="lax",
        )
        return FMUProject(
            path=fmu_dir.base_path,
            project_dir_name=fmu_dir.base_path.name,
            config=fmu_dir.config.load(),
        )
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
