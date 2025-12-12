"""Tests dependencies (middleware)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, create_autospec, patch
from uuid import uuid4

import pytest
from fastapi import Cookie, HTTPException, status
from fastapi.testclient import TestClient
from fmu.settings._init import init_fmu_directory, init_user_fmu_directory
from fmu.settings._resources.lock_manager import LockError
from pydantic import SecretStr

from fmu_settings_api.config import settings
from fmu_settings_api.deps import ProjectSmdaSessionDep, SmdaInterfaceDep
from fmu_settings_api.deps.match import get_match_service
from fmu_settings_api.deps.permissions import (
    check_write_permissions,
    refresh_project_lock_dep,
)
from fmu_settings_api.deps.project import get_project_service
from fmu_settings_api.deps.session import (
    get_project_session,
    get_project_session_no_extend,
    get_project_session_service,
    get_project_session_service_no_extend,
    get_session,
    get_session_no_extend,
    get_session_service,
    get_session_service_no_extend,
)
from fmu_settings_api.deps.smda import get_project_smda_interface
from fmu_settings_api.deps.user_fmu import ensure_user_fmu_directory
from fmu_settings_api.interfaces.smda_api import SmdaAPI
from fmu_settings_api.services.match import MatchService
from fmu_settings_api.services.project import ProjectService
from fmu_settings_api.services.session import SessionService
from fmu_settings_api.session import (
    AccessTokens,
    ProjectSession,
    Session,
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
            "fmu_settings_api.deps.session.session_manager.get_session",
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
            "fmu_settings_api.deps.user_fmu.UserFMUDirectory",
            side_effect=FileNotFoundError("Directory not found"),
        ),
        patch(
            "fmu_settings_api.deps.user_fmu.init_user_fmu_directory",
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
            "fmu_settings_api.deps.user_fmu.UserFMUDirectory",
            side_effect=FileNotFoundError("Directory not found"),
        ),
        patch(
            "fmu_settings_api.deps.user_fmu.init_user_fmu_directory",
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
            "fmu_settings_api.deps.user_fmu.UserFMUDirectory",
            side_effect=FileNotFoundError("Directory not found"),
        ),
        patch(
            "fmu_settings_api.deps.user_fmu.init_user_fmu_directory",
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
            "fmu_settings_api.deps.user_fmu.UserFMUDirectory",
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


async def test_check_write_permissions_not_locked(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> None:
    """Test that check_write_permissions raises 423 when project is not locked."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    mock_lock = Mock()
    mock_lock.is_locked.return_value = False
    project_fmu_dir._lock = mock_lock

    project_session = await add_fmu_project_to_session(session_id, project_fmu_dir)

    with pytest.raises(HTTPException) as exc_info:
        await check_write_permissions(project_session)

    assert exc_info.value.status_code == status.HTTP_423_LOCKED
    assert "Project is not locked" in str(exc_info.value.detail)
    assert "Acquire the lock before writing" in str(exc_info.value.detail)


async def test_check_write_permissions_permission_error(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> None:
    """Test that check_write_permissions raises 403 on PermissionError."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    mock_lock = Mock()
    mock_lock.is_locked.side_effect = PermissionError("Permission denied")
    project_fmu_dir._lock = mock_lock

    project_session = await add_fmu_project_to_session(session_id, project_fmu_dir)

    with pytest.raises(HTTPException) as exc_info:
        await check_write_permissions(project_session)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "Permission denied accessing .fmu" in str(exc_info.value.detail)


async def test_check_write_permissions_file_not_found_error(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> None:
    """Test that check_write_permissions raises 423 on FileNotFoundError."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    mock_lock = Mock()
    mock_lock.is_locked.side_effect = FileNotFoundError("Lock file not found")
    project_fmu_dir._lock = mock_lock

    project_session = await add_fmu_project_to_session(session_id, project_fmu_dir)

    with pytest.raises(HTTPException) as exc_info:
        await check_write_permissions(project_session)

    assert exc_info.value.status_code == status.HTTP_423_LOCKED
    assert "Project lock file is missing" in str(exc_info.value.detail)
    assert "read-only" in str(exc_info.value.detail)


async def test_get_session_no_extend_does_not_extend_expiration(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> None:
    """Tests that get_session_no_extend does not extend session expiration."""
    with pytest.raises(HTTPException, match="401: No active session found"):
        await get_session_no_extend(None)

    with pytest.raises(HTTPException, match="401: Invalid or expired session"):
        await get_session_no_extend(Cookie(default=uuid4()))

    user_fmu_dir = init_user_fmu_directory()
    valid_session = await session_manager.create_session(user_fmu_dir)
    session = await get_session_no_extend(valid_session)
    assert session.user_fmu_directory.path == user_fmu_dir.path

    with (
        patch(
            "fmu_settings_api.deps.session.session_manager.get_session",
            side_effect=Exception("foo"),
        ),
        pytest.raises(HTTPException, match="500: Session error: foo"),
    ):
        await get_session_no_extend(Cookie(default=object))


async def test_get_project_session_no_extend_does_not_extend_expiration(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> None:
    """Tests that get_project_session_no_extend does not extend session expiration."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    with pytest.raises(HTTPException) as exc_info:
        await get_project_session_no_extend(session_id)
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "No FMU project directory open" in str(exc_info.value.detail)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)
    await add_fmu_project_to_session(session_id, project_fmu_dir)

    result = await get_project_session_no_extend(session_id)
    assert isinstance(result, ProjectSession)
    assert result.project_fmu_directory.path == project_fmu_dir.path

    original_expires_at = result.expires_at
    result2 = await get_project_session_no_extend(session_id)
    assert result2.expires_at == original_expires_at

    project_fmu_dir.path.parent.rename(tmp_path_mocked_home / "deleted")
    with pytest.raises(HTTPException) as exc_info:
        await get_project_session_no_extend(session_id)
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert "Project .fmu directory not found" in str(exc_info.value.detail)


async def test_get_project_session_extends_expiration(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> None:
    """Tests that get_project_session extends session expiration."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)
    await add_fmu_project_to_session(session_id, project_fmu_dir)

    result = await get_project_session(session_id)
    original_expires_at = result.expires_at

    result2 = await get_project_session(session_id)
    assert result2.expires_at > original_expires_at


async def test_get_session_service_returns_session_service(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> None:
    """Tests that get_session_service returns a SessionService instance."""
    user_fmu_dir = init_user_fmu_directory()
    valid_session = await session_manager.create_session(user_fmu_dir)
    session = await get_session(valid_session)

    service = await get_session_service(session)
    assert isinstance(service, SessionService)
    assert service._session == session
    assert isinstance(service._session, Session)


async def test_get_session_service_no_extend_does_not_extend_expiration(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> None:
    """Tests that get_session_service_no_extend does not extend session expiration."""
    user_fmu_dir = init_user_fmu_directory()
    valid_session = await session_manager.create_session(user_fmu_dir)
    session = await get_session_no_extend(valid_session)

    service = await get_session_service_no_extend(session)
    assert isinstance(service, SessionService)
    assert service._session == session
    assert isinstance(service._session, Session)

    original_expires_at = session.expires_at
    session2 = await get_session_no_extend(valid_session)
    service2 = await get_session_service_no_extend(session2)
    assert service2._session.expires_at == original_expires_at


async def test_get_project_session_service_returns_session_service(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> None:
    """Tests that get_project_session_service returns a SessionService instance."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)
    await add_fmu_project_to_session(session_id, project_fmu_dir)

    project_session = await get_project_session(session_id)
    service = await get_project_session_service(project_session)

    assert isinstance(service, SessionService)
    assert service._session == project_session
    assert isinstance(service._session, ProjectSession)
    assert service._session.project_fmu_directory.path == project_fmu_dir.path


async def test_get_project_session_service_no_extend_does_not_extend_expiration(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> None:
    """Tests that get_project_session_service_no_extend does not extend expiration."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)
    await add_fmu_project_to_session(session_id, project_fmu_dir)

    project_session = await get_project_session_no_extend(session_id)
    service = await get_project_session_service_no_extend(project_session)

    assert isinstance(service, SessionService)
    assert service._session == project_session
    assert isinstance(service._session, ProjectSession)
    assert service._session.project_fmu_directory.path == project_fmu_dir.path

    original_expires_at = project_session.expires_at
    project_session2 = await get_project_session_no_extend(session_id)
    service2 = await get_project_session_service_no_extend(project_session2)
    assert service2._session.expires_at == original_expires_at


async def test_get_project_service_returns_project_service(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> None:
    """Tests that get_project_service returns a ProjectService instance."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)
    await add_fmu_project_to_session(session_id, project_fmu_dir)

    project_session = await get_project_session(session_id)
    project_service = await get_project_service(project_session)

    assert isinstance(project_service, ProjectService)
    assert project_service._fmu_dir == project_fmu_dir
    assert project_service._fmu_dir.path == project_fmu_dir.path


async def test_refresh_lock_dep_refreshes_lock_when_acquired(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> None:
    """Tests that RefreshLockDep refreshes the lock when it is acquired."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    mock_lock = Mock()
    mock_lock.is_acquired.return_value = True
    mock_lock.refresh = Mock()
    project_fmu_dir._lock = mock_lock

    await add_fmu_project_to_session(session_id, project_fmu_dir)

    await refresh_project_lock_dep(session_id)
    mock_lock.refresh.assert_called_once()


async def test_refresh_lock_dep_does_nothing_when_not_acquired(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> None:
    """Tests that RefreshLockDep does nothing when lock is not acquired."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    mock_lock = Mock()
    mock_lock.is_acquired.return_value = False
    mock_lock.refresh = Mock()
    project_fmu_dir._lock = mock_lock

    await add_fmu_project_to_session(session_id, project_fmu_dir)

    await refresh_project_lock_dep(session_id)
    mock_lock.refresh.assert_not_called()


async def test_refresh_lock_dep_handles_lock_error(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> None:
    """Tests that RefreshLockDep handles lock errors gracefully."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    mock_lock = Mock()
    mock_lock.is_acquired.return_value = True
    mock_lock.refresh.side_effect = LockError("Lock refresh failed")
    project_fmu_dir._lock = mock_lock

    await add_fmu_project_to_session(session_id, project_fmu_dir)

    await refresh_project_lock_dep(session_id)
    session = await session_manager.get_session(session_id, extend_expiration=False)
    assert isinstance(session, ProjectSession)
    assert session.lock_errors.refresh is not None
    assert "Lock refresh failed" in session.lock_errors.refresh


async def test_refresh_lock_dep_handles_permission_error(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> None:
    """Tests that RefreshLockDep swallows PermissionError exceptions."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    mock_lock = Mock()
    mock_lock.is_acquired.return_value = True
    mock_lock.refresh.side_effect = PermissionError("Permission denied")
    project_fmu_dir._lock = mock_lock

    await add_fmu_project_to_session(session_id, project_fmu_dir)

    await refresh_project_lock_dep(session_id)


async def test_refresh_lock_dep_no_session_cookie(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> None:
    """Tests that RefreshLockDep raises 401 when no session cookie is provided."""
    with pytest.raises(HTTPException) as exc_info:
        await refresh_project_lock_dep(None)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "No active session found" in str(exc_info.value.detail)


async def test_refresh_lock_dep_no_project_session(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> None:
    """Tests that RefreshLockDep raises 401 when no project session exists."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    with pytest.raises(HTTPException) as exc_info:
        await refresh_project_lock_dep(session_id)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "No FMU project directory open" in str(exc_info.value.detail)


async def test_get_match_service_returns_match_service() -> None:
    """Tests that get_match_service returns a MatchService instance."""
    match_service = await get_match_service()

    assert isinstance(match_service, MatchService)
