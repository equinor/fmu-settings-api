"""Tests for RMS dependencies."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from runrms.api import RmsApiProxy

from fmu_settings_api.deps.rms import (
    get_opened_rms_project,
    get_rms_project_path,
    get_rms_service,
)
from fmu_settings_api.services.rms import RmsService
from fmu_settings_api.session import RmsSession


async def test_get_rms_service() -> None:
    """Test that get_rms_service returns an RmsService instance."""
    rms_service = await get_rms_service()
    assert isinstance(rms_service, RmsService)


async def test_get_rms_project_path_success() -> None:
    """Test getting RMS project path when configured."""
    expected_path = Path("/path/to/rms/project")
    project_service_mock = MagicMock()
    project_service_mock.rms_project_path = expected_path

    result = await get_rms_project_path(project_service_mock)

    assert result == expected_path


async def test_get_rms_project_path_not_configured() -> None:
    """Test that HTTPException is raised when RMS path is not configured."""
    project_service_mock = MagicMock()
    project_service_mock.rms_project_path = None

    with pytest.raises(HTTPException) as exc_info:
        await get_rms_project_path(project_service_mock)

    assert exc_info.value.status_code == 400  # noqa: PLR2004
    assert (
        exc_info.value.detail
        == "RMS project path is not set in the project config file."
    )


async def test_get_opened_rms_project_success() -> None:
    """Test getting opened RMS project when one is open."""
    rms_root_mock = MagicMock(spec=RmsApiProxy)
    rms_project_mock = MagicMock(spec=RmsApiProxy)
    project_session_mock = MagicMock()
    project_session_mock.rms_session = RmsSession(rms_root_mock, rms_project_mock)

    result = await get_opened_rms_project(project_session_mock)

    assert result is rms_project_mock


async def test_get_opened_rms_project_none_open() -> None:
    """Test that HTTPException is raised when no RMS project is open."""
    project_session_mock = MagicMock()
    project_session_mock.rms_session = None

    with pytest.raises(HTTPException) as exc_info:
        await get_opened_rms_project(project_session_mock)

    assert exc_info.value.status_code == 400  # noqa: PLR2004
    assert exc_info.value.detail == (
        "No RMS project is currently open. Please open an RMS project first."
    )
