"""Changelog service dependencies."""

from typing import Annotated

from fastapi import Depends

from fmu_settings_api.deps.session import ProjectSessionDep
from fmu_settings_api.services.changelog import ChangelogService


async def get_changelog_service(
    project_session: ProjectSessionDep,
) -> ChangelogService:
    """Returns a ChangelogService instance."""
    return ChangelogService(project_session.project_fmu_directory)


ChangelogServiceDep = Annotated[ChangelogService, Depends(get_changelog_service)]
