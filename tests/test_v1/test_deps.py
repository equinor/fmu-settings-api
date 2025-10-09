"""Tests dependencies (middleware)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, create_autospec, patch
from uuid import uuid4

import pytest
from fastapi import Cookie, HTTPException, status
from fastapi.testclient import TestClient
from fmu.settings._init import init_fmu_directory, init_user_fmu_directory
from pydantic import SecretStr

from fmu_settings_api.config import settings
from fmu_settings_api.deps import (
    ProjectSmdaSessionDep,
    SmdaInterfaceDep,
    check_write_permissions,
    ensure_user_fmu_directory,
    get_project_smda_interface,
    get_session,
)
from fmu_settings_api.interfaces.smda_api import SmdaAPI
from fmu_settings_api.session import (
    AccessTokens,
    SessionManager,
    add_fmu_project_to_session,
)

ROUTE = "/api/v1/health"


async def test_get_session_dep(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> None:
    """Tests the get_session dependency."""
    with pytest.raises(HTTPException, match="401: No active session found"):
        await get_session(None)

    with pytest.raises(HTTPException, match="401: Invalid or expired session"):
        await get_session(Cookie(default=uuid4()))

    user_fmu_dir = init_user_fmu_directory()
    valid_session = await session_manager.create_session(user_fmu_dir)
    session = await get_session(valid_session)
    assert session.user_fmu_directory.path == user_fmu_dir.path

    with (
        patch(
            "fmu_settings_api.deps.session_manager.get_session",
            side_effect=Exception("foo"),
        ),
        pytest.raises(HTTPException, match="500: Session error: foo"),
    ):
        await get_session(Cookie(default=object))


def test_get_session_dep_from_request(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 401 returns when session id is not valid."""
    client_with_session.cookies.set(settings.SESSION_COOKIE_KEY, str(uuid4()))
    response = client_with_session.get(ROUTE)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()


async def test_get_smda_interface(tmp_path_mocked_home: Path) -> None:
    """Tests the get_smda_interface dependency."""
    smda_api_token_mock = "test_token"
    smda_subscription_mock = "test_subscription"
    user_fmu_directory = init_user_fmu_directory()
    user_fmu_directory.set_config_value(
        "user_api_keys.smda_subscription", smda_subscription_mock
    )

    session_mock = create_autospec(SmdaInterfaceDep, instance=True)
    session_mock.id = str(uuid4())
    session_mock.created_at = datetime.now(UTC)
    session_mock.expires_at = timedelta(seconds=60)
    session_mock.last_accessed = datetime.now(UTC)
    session_mock.access_tokens = AccessTokens(
        fmu_settings=SecretStr("fmu_settings_token")
    )
    session_mock.user_fmu_directory = user_fmu_directory

    with pytest.raises(HTTPException, match="401: SMDA access token is not set"):
        await get_project_smda_interface(session_mock)

    session_mock.access_tokens = AccessTokens(
        fmu_settings=SecretStr("fmu_settings_token"),
        smda_api=SecretStr(smda_api_token_mock),
    )

    smda_project_interface: SmdaAPI = await get_project_smda_interface(session_mock)
    assert isinstance(smda_project_interface, SmdaAPI)
    assert smda_project_interface._access_token == smda_api_token_mock
    assert smda_project_interface._subscription_key == smda_subscription_mock


async def test_get_project_smda_interface(tmp_path_mocked_home: Path) -> None:
    """Tests the get_project_smda_interface dependency."""
    smda_api_token_mock = "test_token"
    smda_subscription_mock = "test_subscription"
    user_fmu_directory = init_user_fmu_directory()
    user_fmu_directory.set_config_value(
        "user_api_keys.smda_subscription", smda_subscription_mock
    )

    project_session_mock = create_autospec(ProjectSmdaSessionDep, instance=True)
    project_session_mock.id = str(uuid4())
    project_session_mock.created_at = datetime.now(UTC)
    project_session_mock.expires_at = timedelta(seconds=60)
    project_session_mock.last_accessed = datetime.now(UTC)
    project_session_mock.access_tokens = AccessTokens(
        fmu_settings=SecretStr("fmu_settings_token")
    )
    project_session_mock.user_fmu_directory = user_fmu_directory

    with pytest.raises(HTTPException, match="401: SMDA access token is not set"):
        await get_project_smda_interface(project_session_mock)

    project_session_mock.access_tokens = AccessTokens(
        fmu_settings=SecretStr("fmu_settings_token"),
        smda_api=SecretStr(smda_api_token_mock),
    )

    smda_interface = await get_project_smda_interface(project_session_mock)
    assert isinstance(smda_interface, SmdaAPI)
    assert smda_interface._access_token == smda_api_token_mock
    assert smda_interface._subscription_key == smda_subscription_mock


async def test_ensure_user_fmu_directory_file_exists_error() -> None:
    """Test that a FileExistsError results in HTTPException with status 409."""
    with (
        patch(
            "fmu_settings_api.deps.UserFMUDirectory",
            side_effect=FileNotFoundError("Directory not found"),
        ),
        patch(
            "fmu_settings_api.deps.init_user_fmu_directory",
            side_effect=FileExistsError("Directory already exists"),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await ensure_user_fmu_directory()

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert "User .fmu already exists but is invalid" in str(exc_info.value.detail)


async def test_ensure_user_fmu_directory_permission_error() -> None:
    """Test that a PermissionError results in HTTPException with status 403."""
    with (
        patch(
            "fmu_settings_api.deps.UserFMUDirectory",
            side_effect=FileNotFoundError("Directory not found"),
        ),
        patch(
            "fmu_settings_api.deps.init_user_fmu_directory",
            side_effect=PermissionError("Permission denied"),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await ensure_user_fmu_directory()

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "Permission denied creating user .fmu" in str(exc_info.value.detail)


async def test_ensure_user_fmu_directory_general_error() -> None:
    """Test that a general Exception results in HTTPException with status 500."""
    with (
        patch(
            "fmu_settings_api.deps.UserFMUDirectory",
            side_effect=FileNotFoundError("Directory not found"),
        ),
        patch(
            "fmu_settings_api.deps.init_user_fmu_directory",
            side_effect=Exception("Something went wrong"),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await ensure_user_fmu_directory()

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Something went wrong" in str(exc_info.value.detail)


async def test_ensure_user_fmu_directory_outer_general_error() -> None:
    """Test that a general Exception from UserFMUDirectory results in HTTP 500."""
    with (
        patch(
            "fmu_settings_api.deps.UserFMUDirectory",
            side_effect=RuntimeError("Outer exception"),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await ensure_user_fmu_directory()

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Outer exception" in str(exc_info.value.detail)


async def test_check_write_permissions_project_not_acquired(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> None:
    """Test that check_write_permissions raises HTTPException when not acquired."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    mock_lock = Mock()
    mock_lock.is_acquired.return_value = False
    project_fmu_dir._lock = mock_lock

    project_session = await add_fmu_project_to_session(session_id, project_fmu_dir)

    with pytest.raises(HTTPException) as exc_info:
        await check_write_permissions(project_session)

    assert exc_info.value.status_code == status.HTTP_423_LOCKED
    assert "Project is read-only" in str(exc_info.value.detail)
    assert "locked by another process" in str(exc_info.value.detail)
