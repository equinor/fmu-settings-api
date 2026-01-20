"""RMS service dependencies."""

from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException
from runrms.api import RmsApiProxy

from fmu_settings_api.services.rms import RmsService

from .project import ProjectServiceDep
from .session import ProjectSessionDep


async def get_rms_service() -> RmsService:
    """Returns an RmsService instance."""
    return RmsService()


RmsServiceDep = Annotated[RmsService, Depends(get_rms_service)]


async def get_rms_project_path(project_service: ProjectServiceDep) -> Path:
    """Returns the RMS project path configured in the project."""
    rms_project_path = project_service.rms_project_path
    if rms_project_path is None:
        raise HTTPException(
            status_code=400,
            detail="RMS project path is not set in the project config file.",
        )
    return rms_project_path


RmsProjectPathDep = Annotated[Path, Depends(get_rms_project_path)]


async def get_opened_rms_project(
    project_session: ProjectSessionDep,
) -> RmsApiProxy:
    """Returns the opened RMS project from the session."""
    if project_session.rms_session is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "No RMS project is currently open. Please open an RMS project first."
            ),
        )
    return project_session.rms_session.project


RmsProjectDep = Annotated[RmsApiProxy, Depends(get_opened_rms_project)]
