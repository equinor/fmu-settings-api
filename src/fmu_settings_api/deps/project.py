"""Project service dependencies."""

from typing import Annotated

from fastapi import Depends

from fmu_settings_api.services.project import ProjectService

from .session import ProjectSessionDep, ProjectSessionNoExtendDep


async def get_project_service(
    project_session: ProjectSessionDep,
) -> ProjectService:
    """Returns a ProjectService instance for the project session."""
    return ProjectService(project_session.project_fmu_directory)


async def get_project_service_no_extend(
    project_session: ProjectSessionNoExtendDep,
) -> ProjectService:
    """Returns a ProjectService instance without extending session expiration."""
    return ProjectService(project_session.project_fmu_directory)


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
ProjectServiceNoExtendDep = Annotated[
    ProjectService, Depends(get_project_service_no_extend)
]
