"""ERT service dependencies."""

from typing import Annotated

from fastapi import Depends

from fmu_settings_api.services.ert import ErtService

from .session import ProjectSessionDep


async def get_ert_service(project_session: ProjectSessionDep) -> ErtService:
    """Returns an ErtService instance for the project session."""
    return ErtService(project_session.project_fmu_directory)


ErtServiceDep = Annotated[ErtService, Depends(get_ert_service)]
