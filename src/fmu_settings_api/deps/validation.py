"""Project validation service dependencies."""

from typing import Annotated

from fastapi import Depends

from fmu_settings_api.deps.session import ProjectSessionDep
from fmu_settings_api.deps.smda import ProjectSmdaServiceDep
from fmu_settings_api.services.project_validation import ProjectValidationService


async def get_project_validation_service(
    project_session: ProjectSessionDep,
    smda_service: ProjectSmdaServiceDep,
) -> ProjectValidationService:
    """Returns a ProjectValidationService instance."""
    return ProjectValidationService(
        project_session.project_fmu_directory,
        smda_service,
    )


ProjectValidationServiceDep = Annotated[
    ProjectValidationService, Depends(get_project_validation_service)
]
