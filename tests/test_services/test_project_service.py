"""Tests for ProjectService."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fmu.settings import ProjectFMUDirectory

from fmu_settings_api.services.project import ProjectService


def test_rms_project_path_returns_path(fmu_dir: ProjectFMUDirectory) -> None:
    """Test that rms_project_path property returns the path from config."""
    expected_path = Path("/path/to/rms/project")
    service = ProjectService(fmu_dir)
    fmu_dir.set_config_value("rms", {"path": expected_path, "version": "14.2.2"})

    assert service.rms_project_path == expected_path


def test_rms_project_path_returns_none(fmu_dir: ProjectFMUDirectory) -> None:
    """Test that rms_project_path property returns None when not set."""
    service = ProjectService(fmu_dir)

    assert service.rms_project_path is None


def test_update_rms_saves_path_and_version(fmu_dir: ProjectFMUDirectory) -> None:
    """Test that update_rms saves the RMS project path and version."""
    rms_project_path = Path("/path/to/rms/project.rms14.2.2")
    service = ProjectService(fmu_dir)

    with patch(
        "fmu_settings_api.services.project.RmsService.get_rms_version",
        return_value="14.2.2",
    ):
        rms_config = service.update_rms(rms_project_path)

    assert rms_config.path == rms_project_path
    assert rms_config.version == "14.2.2"
    saved_config = fmu_dir.config.load().rms
    assert saved_config is not None
    assert saved_config.path == rms_project_path
    assert saved_config.version == "14.2.2"


def test_rms_project_path_missing_path_value(fmu_dir: ProjectFMUDirectory) -> None:
    """Test that rms_project_path returns None when rms config lacks a path."""
    service = ProjectService(fmu_dir)

    with patch.object(fmu_dir, "get_config_value", return_value=None) as mock_get:
        assert service.rms_project_path is None
        mock_get.assert_called_once_with("rms.path", None)


def test_update_rms_missing_project_path_raises_file_not_found(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test update_rms raises FileNotFoundError when RMS path is missing."""
    rms_project_path = Path("/path/to/rms/project.rms14.2.2")
    service = ProjectService(fmu_dir)

    with (
        patch(
            "fmu_settings_api.services.project.RmsService.get_rms_version",
            side_effect=FileNotFoundError("not found"),
        ),
        pytest.raises(FileNotFoundError) as exc_info,
    ):
        service.update_rms(rms_project_path)

    assert "does not exist" in str(exc_info.value)
    assert fmu_dir.config.load().rms is None
