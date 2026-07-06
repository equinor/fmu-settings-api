"""Tests for project validation dependencies."""

from unittest.mock import MagicMock

from fmu_settings_api.deps.validation import get_project_validation_service
from fmu_settings_api.services.project_validation import ProjectValidationService


async def test_get_project_validation_service() -> None:
    """Test that get_project_validation_service returns a validation service."""
    project_session = MagicMock()
    project_fmu_directory = MagicMock()
    project_session.project_fmu_directory = project_fmu_directory
    smda_service = MagicMock()

    validation_service = await get_project_validation_service(
        project_session, smda_service
    )

    assert isinstance(validation_service, ProjectValidationService)
    assert validation_service._fmu_dir is project_fmu_directory
    assert validation_service._smda_service is smda_service
