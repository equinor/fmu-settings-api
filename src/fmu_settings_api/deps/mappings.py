"""Mappings service dependencies."""

from typing import Annotated

from fastapi import Depends

from fmu_settings_api.deps.session import ProjectSessionDep
from fmu_settings_api.services.mappings import MappingsService


async def get_mappings_service(
    project_session: ProjectSessionDep,
) -> MappingsService:
    """Returns an MappingsService instance."""
    return MappingsService(project_session.project_fmu_directory)


MappingsServiceDep = Annotated[MappingsService, Depends(get_mappings_service)]
