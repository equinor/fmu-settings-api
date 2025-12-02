"""Tests for ProjectService."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fmu_settings_api.services.project import ProjectService


def test_rms_project_path_returns_path() -> None:
    """Test that rms_project_path property returns the path from config."""
    mock_fmu_dir = MagicMock()
    expected_path = Path("/path/to/rms/project")
    mock_rms = MagicMock()
    mock_rms.path = expected_path
    mock_fmu_dir.config.load.return_value.rms = mock_rms

    service = ProjectService(mock_fmu_dir)

    assert service.rms_project_path == expected_path
    mock_fmu_dir.config.load.assert_called_once()


def test_rms_project_path_returns_none() -> None:
    """Test that rms_project_path property returns None when not set."""
    mock_fmu_dir = MagicMock()
    mock_fmu_dir.config.load.return_value.rms = None

    service = ProjectService(mock_fmu_dir)

    assert service.rms_project_path is None
    mock_fmu_dir.config.load.assert_called_once()


def test_update_rms_saves_path_and_version() -> None:
    """Test that update_rms saves the RMS project path and version."""
    mock_fmu_dir = MagicMock()
    rms_project_path = Path("/path/to/rms/project.rms14.2.2")

    mock_rms_project_info = MagicMock()
    mock_rms_project_info.master.version = "14.2.2"

    service = ProjectService(mock_fmu_dir)

    with patch(
        "fmu_settings_api.services.rms.RmsProject.from_filepath",
        return_value=mock_rms_project_info,
    ):
        success, version = service.update_rms(rms_project_path)

    assert success is True
    assert version == "14.2.2"
    mock_fmu_dir.set_config_value.assert_called_once_with(
        "rms",
        {
            "path": rms_project_path,
            "version": "14.2.2",
        },
    )


def test_rms_project_path_missing_path_value() -> None:
    """Test that rms_project_path returns None when rms config lacks a path."""
    mock_fmu_dir = MagicMock()
    mock_rms = MagicMock()
    mock_rms.path = None
    mock_fmu_dir.config.load.return_value.rms = mock_rms

    service = ProjectService(mock_fmu_dir)

    assert service.rms_project_path is None
    mock_fmu_dir.config.load.assert_called_once()


def test_update_rms_missing_project_path_raises_file_not_found() -> None:
    """Test update_rms raises FileNotFoundError when RMS path is missing."""
    mock_fmu_dir = MagicMock()
    rms_project_path = Path("/path/to/rms/project.rms14.2.2")

    with patch(
        "fmu_settings_api.services.project.RmsService.get_rms_version",
        side_effect=FileNotFoundError("not found"),
    ):
        service = ProjectService(mock_fmu_dir)
        with pytest.raises(FileNotFoundError) as exc_info:
            service.update_rms(rms_project_path)

    assert "does not exist" in str(exc_info.value)
    mock_fmu_dir.set_config_value.assert_not_called()
