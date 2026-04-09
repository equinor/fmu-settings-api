"""Project service dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException

from fmu_settings_api.services.project import ProjectService
from fmu_settings_api.session import ProjectSession

from .session import ProjectSessionDep, SessionDep


async def get_project_service(
    project_session: ProjectSessionDep,
) -> ProjectService:
    """Returns a ProjectService instance for the project session."""
    return ProjectService(project_session.project_fmu_directory)


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]


async def get_project_service_for_restore(
    session: SessionDep,
) -> ProjectService:
    """Returns a ProjectService for restore routes, even if .fmu is deleted."""
    if not isinstance(session, ProjectSession):
        raise HTTPException(
            status_code=401,
            detail="No FMU project directory open",
        )

    return ProjectService(session.project_fmu_directory)


ProjectServiceForRestoreDep = Annotated[
    ProjectService, Depends(get_project_service_for_restore)
]
