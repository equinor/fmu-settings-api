"""Resource service dependencies."""

from typing import Annotated

from fastapi import Depends

from fmu_settings_api.services.resource import ResourceService

from .session import ProjectSessionDep


async def get_resource_service(
    project_session: ProjectSessionDep,
) -> ResourceService:
    """Returns a ResourceService instance for the project session."""
    return ResourceService(project_session.project_fmu_directory)


ResourceServiceDep = Annotated[ResourceService, Depends(get_resource_service)]
