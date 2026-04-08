"""Tests for RMS dependencies."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from runrms.api import RmsApiProxy
from runrms.executor import ApiExecutor

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

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert (
        exc_info.value.detail
        == "RMS project path is not set in the project config file."
    )


async def test_get_opened_rms_project_success() -> None:
    """Test getting opened RMS project refreshes the RMS session expiry."""
    rms_executor_mock = MagicMock(spec=ApiExecutor)
    rms_project_mock = MagicMock(spec=RmsApiProxy)
    project_session_mock = MagicMock()
    rms_session_expires_at = datetime.now(UTC) + timedelta(seconds=5)
    project_session_mock.rms_session = RmsSession(
        rms_executor_mock, rms_project_mock, rms_session_expires_at
    )

    refreshed_rms_session = RmsSession(
        rms_executor_mock,
        rms_project_mock,
        datetime.now(UTC) + timedelta(seconds=30),
    )

    with patch(
        "fmu_settings_api.deps.rms.refresh_rms_session",
        new_callable=AsyncMock,
        return_value=refreshed_rms_session,
    ) as mock_refresh_rms_session:
        result = await get_opened_rms_project(project_session_mock)

    assert result is rms_project_mock
    mock_refresh_rms_session.assert_awaited_once_with(project_session_mock)


async def test_get_opened_rms_project_none_open() -> None:
    """Test that missing RMS project returns 400 without attempting refresh."""
    project_session_mock = MagicMock()
    project_session_mock.rms_session = None

    with (
        patch(
            "fmu_settings_api.deps.rms.refresh_rms_session",
            new_callable=AsyncMock,
        ) as mock_refresh_rms_session,
        pytest.raises(HTTPException) as exc_info,
    ):
        await get_opened_rms_project(project_session_mock)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == (
        "No RMS project is currently open. Please open an RMS project first."
    )
    mock_refresh_rms_session.assert_not_awaited()
