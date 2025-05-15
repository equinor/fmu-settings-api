"""Routes to operate on the .fmu config file."""

from fastapi import APIRouter, HTTPException
from fmu.settings.models.project_config import ProjectConfig

from fmu_settings_api.deps import SessionDep

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/", response_model=ProjectConfig)
async def get_fmu_directory_config(session: SessionDep) -> ProjectConfig:
    """Returns the configuration for the currently open FMU Directory session."""
    try:
        config = session.fmu_directory.config
        return config.load()
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied loading .fmu config at {config.path}",
        ) from e
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404, detail=f".fmu config at {config.path} does not exist"
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
