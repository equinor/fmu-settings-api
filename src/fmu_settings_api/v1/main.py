"""The main router for /api/v1."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from fmu.settings import get_fmu_directory as _get_fmu_directory
from fmu.settings._init import init_fmu_directory as _init_fmu_directory
from fmu.settings.resources.config import Config
from fmu_settings_api.config import settings
from fmu_settings_api.deps import verify_auth_token

api_v1_router = APIRouter(
    prefix=settings.API_V1_PREFIX,
    tags=["v1"],
    dependencies=[Depends(verify_auth_token)],
)


class FMUDirPath(BaseModel):
    """Path where a .fmu directory may exist."""

    path: Path
    """Path to the directory which should or will contain a .fmu directory."""


@api_v1_router.post("/fmu")
async def get_fmu_directory(fmu_dir_path: FMUDirPath) -> Config:
    """Returns the configuration for the .fmu directory at 'path'."""
    path = fmu_dir_path.path
    try:
        fmu_dir = _get_fmu_directory(path)
        return fmu_dir.config.load()
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


@api_v1_router.post("/fmu/init")
async def init_fmu_directory(fmu_dir_path: FMUDirPath) -> Config:
    """Initializes .fmu at 'path' and returns its configuration."""
    path = fmu_dir_path.path
    try:
        fmu_dir = _init_fmu_directory(path)
        return fmu_dir.config.load()
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


@api_v1_router.get("/health")
async def v1_health_check() -> dict[str, str]:
    """Simple health check endpoint."""
    return {"status": "ok"}
