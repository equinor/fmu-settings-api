"""Tests for ProjectService."""

from pathlib import Path
from unittest.mock import MagicMock

from fmu_settings_api.services.project import ProjectService


def test_rms_project_path_returns_path() -> None:
    """Test that rms_project_path property returns the path from config."""
    mock_fmu_dir = MagicMock()
    expected_path = Path("/path/to/rms/project")
    mock_fmu_dir.config.load.return_value.rms_project_path = expected_path

    service = ProjectService(mock_fmu_dir)

    assert service.rms_project_path == expected_path
    mock_fmu_dir.config.load.assert_called_once()


def test_rms_project_path_returns_none() -> None:
    """Test that rms_project_path property returns None when not set."""
    mock_fmu_dir = MagicMock()
    mock_fmu_dir.config.load.return_value.rms_project_path = None

    service = ProjectService(mock_fmu_dir)

    assert service.rms_project_path is None
    mock_fmu_dir.config.load.assert_called_once()
