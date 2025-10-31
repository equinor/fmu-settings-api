"""Project service dependencies."""

from typing import Annotated

from fastapi import Depends

from fmu_settings_api.services.project import ProjectService

from .session import ProjectSessionDep


async def get_project_service(
    project_session: ProjectSessionDep,
) -> ProjectService:
    """Returns a ProjectService instance for the project session."""
    return ProjectService(project_session.project_fmu_directory)


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
