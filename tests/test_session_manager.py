"""Tests the SessionManager functionality."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from fmu.settings._init import init_fmu_directory, init_user_fmu_directory
from fmu.settings._resources.lock_manager import LockError
from pydantic import SecretStr

from fmu_settings_api.config import settings
from fmu_settings_api.models.common import AccessToken
from fmu_settings_api.session import (
    ProjectSession,
    RmsSession,
    Session,
    SessionManager,
    SessionNotFoundError,
    add_access_token_to_session,
    add_fmu_project_to_session,
    add_rms_project_to_session,
    create_fmu_session,
    destroy_fmu_session,
    remove_fmu_project_from_session,
    remove_rms_project_from_session,
    session_manager,
    try_acquire_project_lock,
)


@pytest.fixture
def mock_rms_root() -> MagicMock:
    """Returns a mock RMS API root proxy."""
    return MagicMock(_shutdown=MagicMock())


@pytest.fixture
def mock_rms_project() -> MagicMock:
    """Returns a mock RMS API Project proxy."""
    return MagicMock(close=MagicMock())


def test_session_manager_init() -> None:
    """Tests initialization of the SessionManager."""
    assert session_manager.storage == SessionManager().storage == {}


async def test_create_session(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests creating a new session."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)
    assert session_id in session_manager.storage
    assert session_manager.storage[session_id].user_fmu_directory == user_fmu_dir
    assert len(session_manager.storage) == 1


async def test_create_session_wrapper(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests creating a new session with the wrapper."""
    user_fmu_dir = init_user_fmu_directory()
    with patch("fmu_settings_api.session.session_manager", session_manager):
        session_id = await create_fmu_session(user_fmu_dir)
    assert session_id in session_manager.storage
    assert session_manager.storage[session_id].user_fmu_directory == user_fmu_dir
    assert len(session_manager.storage) == 1


async def test_get_non_existing_session(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests getting an existing session."""
    user_fmu_dir = init_user_fmu_directory()
    await session_manager.create_session(user_fmu_dir)
    with pytest.raises(SessionNotFoundError, match="No active session found"):
        await session_manager.get_session("no")
    assert len(session_manager.storage) == 1


async def test_get_existing_session(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests getting an existing session."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)
    session = await session_manager.get_session(session_id)
    assert session == session_manager.storage[session_id]
    assert len(session_manager.storage) == 1


async def test_get_existing_session_expiration(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests getting an existing session expires."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)
    orig_session = session_manager.storage[session_id]
    expiration_duration = timedelta(seconds=settings.SESSION_EXPIRE_SECONDS)
    assert orig_session.created_at + expiration_duration == orig_session.expires_at

    # Pretend it expired a second ago.
    orig_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(SessionNotFoundError, match="Invalid or expired session"):
        assert await session_manager.get_session(session_id)
    # It should also be destroyed.
    assert session_id not in session_manager.storage
    assert len(session_manager.storage) == 0


async def test_get_existing_session_updates_last_accessed(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests getting an existing session updates its last accessed."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)
    orig_session = deepcopy(session_manager.storage[session_id])
    session = await session_manager.get_session(session_id)
    assert session is not None
    assert orig_session.last_accessed < session.last_accessed


async def test_get_existing_session_updates_expires_at(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests getting an existing session updates its expiration."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)
    orig_session = deepcopy(session_manager.storage[session_id])
    session = await session_manager.get_session(session_id)
    assert session is not None
    assert (
        orig_session.last_accessed + timedelta(seconds=settings.SESSION_EXPIRE_SECONDS)
        < session.expires_at
    )
    assert orig_session.expires_at < session.expires_at


async def test_get_existing_session_does_not_update_expires_at(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests getting an existing session doesn't update expiration if not extended."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)
    orig_session = deepcopy(session_manager.storage[session_id])
    session = await session_manager.get_session(session_id, extend_expiration=False)
    assert session is not None
    # Last accessed changed
    assert orig_session.last_accessed < session.last_accessed
    # But same expiration
    assert orig_session.expires_at == session.expires_at


async def test_try_acquire_project_lock_acquires_when_not_held(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests that try_acquire_project_lock acquires the lock when not already held."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "lock_acquire_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    mock_lock = Mock()
    mock_lock.is_acquired.return_value = False
    mock_lock.acquire = Mock()
    project_fmu_dir._lock = mock_lock

    with patch("fmu_settings_api.session.session_manager", session_manager):
        await add_fmu_project_to_session(session_id, project_fmu_dir)
        mock_lock.reset_mock()
        result = await try_acquire_project_lock(session_id)

    assert isinstance(result, ProjectSession)
    assert mock_lock.is_acquired.call_count == 1  # noqa: PLR2004
    mock_lock.acquire.assert_called_once_with()
    assert result.lock_errors.acquire is None


async def test_try_acquire_project_lock_records_acquire_error(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests that lock acquire failures are captured by try_acquire_project_lock."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "lock_acquire_error_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    mock_lock = Mock()
    mock_lock.is_acquired.return_value = False
    mock_lock.acquire = Mock(side_effect=LockError("Acquire failed"))
    project_fmu_dir._lock = mock_lock

    with patch("fmu_settings_api.session.session_manager", session_manager):
        await add_fmu_project_to_session(session_id, project_fmu_dir)
        mock_lock.reset_mock()
        result = await try_acquire_project_lock(session_id)

    assert isinstance(result, ProjectSession)
    assert mock_lock.is_acquired.call_count == 1  # noqa: PLR2004
    mock_lock.acquire.assert_called_once_with()
    assert result.lock_errors.acquire == "Acquire failed"


async def test_try_acquire_project_lock_requires_project_session(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests that try_acquire_project_lock requires a project-scoped session."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    with (
        patch("fmu_settings_api.session.session_manager", session_manager),
        pytest.raises(SessionNotFoundError, match="No FMU project directory open"),
    ):
        await try_acquire_project_lock(session_id)


async def test_try_acquire_project_lock_handles_is_acquired_error(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests that try_acquire_project_lock tolerates lock status errors."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "lock_status_error_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    mock_lock = Mock()
    mock_lock.is_acquired.side_effect = LockError("status failed")
    mock_lock.refresh = Mock()
    mock_lock.acquire = Mock()
    project_fmu_dir._lock = mock_lock

    with patch("fmu_settings_api.session.session_manager", session_manager):
        await add_fmu_project_to_session(session_id, project_fmu_dir)
        mock_lock.reset_mock()
        result = await try_acquire_project_lock(session_id)

    assert isinstance(result, ProjectSession)
    assert mock_lock.is_acquired.call_count == 1  # noqa: PLR2004
    mock_lock.refresh.assert_not_called()
    mock_lock.acquire.assert_not_called()


async def test_destroy_fmu_session(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests destroying a session."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)
    with patch("fmu_settings_api.session.session_manager", session_manager):
        await destroy_fmu_session(session_id)
    assert session_id not in session_manager.storage
    assert len(session_manager.storage) == 0


async def test_add_valid_access_token_to_session(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests adding an access token to a session."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    session = await session_manager.get_session(session_id)
    assert session.access_tokens.smda_api is None

    token = AccessToken(id="smda_api", key=SecretStr("secret"))
    await add_access_token_to_session(session_id, token)

    session = await session_manager.get_session(session_id)
    assert session.access_tokens.smda_api is not None

    # Assert obfuscated
    assert str(session.access_tokens.smda_api) == "*" * 10


async def test_add_invalid_access_token_to_session(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests adding an invalid access token to a session."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    session = await session_manager.get_session(session_id)
    assert session.access_tokens.smda_api is None

    token = AccessToken(id="foo", key=SecretStr("secret"))
    with pytest.raises(ValueError, match="Invalid access token id"):
        await add_access_token_to_session(session_id, token)


async def test_add_fmu_project_to_session_acquires_lock(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests that adding an FMU project to a session acquires the lock."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    mock_lock = Mock()
    project_fmu_dir._lock = mock_lock

    with patch("fmu_settings_api.session.session_manager", session_manager):
        await add_fmu_project_to_session(session_id, project_fmu_dir)

    mock_lock.acquire.assert_called_once()


async def test_add_fmu_project_to_session_releases_previous_lock(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests that adding a new project releases the previous project's lock."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project1_path = tmp_path_mocked_home / "test_project1"
    project1_path.mkdir()
    project1_fmu_dir = init_fmu_directory(project1_path)

    project2_path = tmp_path_mocked_home / "test_project2"
    project2_path.mkdir()
    project2_fmu_dir = init_fmu_directory(project2_path)

    mock_lock1 = Mock()
    mock_lock2 = Mock()
    project1_fmu_dir._lock = mock_lock1
    project2_fmu_dir._lock = mock_lock2

    with patch("fmu_settings_api.session.session_manager", session_manager):
        await add_fmu_project_to_session(session_id, project1_fmu_dir)
        mock_lock1.acquire.assert_called_once()

        await add_fmu_project_to_session(session_id, project2_fmu_dir)
        mock_lock1.release.assert_called_once()
        mock_lock2.acquire.assert_called_once()


async def test_remove_fmu_project_from_session_releases_lock(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests that removing an FMU project from a session releases the lock."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    mock_lock = Mock()
    project_fmu_dir._lock = mock_lock

    with patch("fmu_settings_api.session.session_manager", session_manager):
        await add_fmu_project_to_session(session_id, project_fmu_dir)
        mock_lock.acquire.assert_called_once()

        await remove_fmu_project_from_session(session_id)
        mock_lock.release.assert_called_once()


async def test_remove_fmu_project_from_session_handles_lock_release_exception(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests that removing an FMU project handles lock release exceptions gracefully."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    mock_lock = Mock()
    mock_lock.release.side_effect = Exception("Lock release failed")
    project_fmu_dir._lock = mock_lock

    with patch("fmu_settings_api.session.session_manager", session_manager):
        await add_fmu_project_to_session(session_id, project_fmu_dir)
        mock_lock.acquire.assert_called_once()

        result = await remove_fmu_project_from_session(session_id)
        mock_lock.release.assert_called_once()

        assert isinstance(result, Session)
        assert result.id == session_id


async def test_destroy_session_releases_project_lock(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests that destroying a session with a project releases the project lock."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    mock_lock = Mock()
    project_fmu_dir._lock = mock_lock

    with patch("fmu_settings_api.session.session_manager", session_manager):
        await add_fmu_project_to_session(session_id, project_fmu_dir)
        mock_lock.acquire.assert_called_once()

        await session_manager.destroy_session(session_id)
        mock_lock.release.assert_called_once()


async def test_destroy_session_handles_lock_release_exceptions(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests that session destruction handles lock release exceptions gracefully."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    mock_lock = Mock()
    mock_lock.release.side_effect = Exception("Lock release failed")
    project_fmu_dir._lock = mock_lock

    with patch("fmu_settings_api.session.session_manager", session_manager):
        await add_fmu_project_to_session(session_id, project_fmu_dir)

        await session_manager.destroy_session(session_id)

        assert session_id not in session_manager.storage


async def test_lock_error_gracefully_handled_in_add_fmu_project_to_session(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests that LockError is gracefully handled in add_fmu_project_to_session."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    mock_lock = Mock()
    mock_lock.acquire.side_effect = LockError("Project is locked by another process")
    mock_lock.is_acquired.return_value = False
    project_fmu_dir._lock = mock_lock

    with patch("fmu_settings_api.session.session_manager", session_manager):
        project_session = await add_fmu_project_to_session(session_id, project_fmu_dir)

        assert project_session is not None
        assert project_session.project_fmu_directory == project_fmu_dir

        mock_lock.acquire.assert_called_once()
        assert not project_session.project_fmu_directory._lock.is_acquired()


async def test_add_fmu_project_to_session_handles_previous_lock_release_error(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests handling exception when releasing previous lock."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project1_path = tmp_path_mocked_home / "test_project1"
    project1_path.mkdir()
    project1_fmu_dir = init_fmu_directory(project1_path)

    mock_lock1 = Mock()
    project1_fmu_dir._lock = mock_lock1

    project2_path = tmp_path_mocked_home / "test_project2"
    project2_path.mkdir()
    project2_fmu_dir = init_fmu_directory(project2_path)

    mock_lock2 = Mock()
    project2_fmu_dir._lock = mock_lock2

    with patch("fmu_settings_api.session.session_manager", session_manager):
        await add_fmu_project_to_session(session_id, project1_fmu_dir)

        mock_lock1.release.side_effect = Exception("Failed to release lock")

        project_session = await add_fmu_project_to_session(session_id, project2_fmu_dir)

        assert project_session.project_fmu_directory == project2_fmu_dir
        assert project_session.lock_errors.release == "Failed to release lock"

        mock_lock1.release.assert_called_once()
        mock_lock2.acquire.assert_called_once()


async def test_remove_fmu_project_from_session_with_regular_session(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests remove_fmu_project_from_session when session is not a ProjectSession."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    with patch("fmu_settings_api.session.session_manager", session_manager):
        result_session = await remove_fmu_project_from_session(session_id)

        original_session = await session_manager.get_session(session_id)

    assert result_session == original_session


async def test_add_rms_project_to_session_success(
    session_manager: SessionManager,
    tmp_path_mocked_home: Path,
    mock_rms_root: MagicMock,
    mock_rms_project: MagicMock,
) -> None:
    """Test adding an RMS project to a valid project session."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    with patch("fmu_settings_api.session.session_manager", session_manager):
        await add_fmu_project_to_session(session_id, project_fmu_dir)

        result_session = await add_rms_project_to_session(
            session_id, mock_rms_root, mock_rms_project
        )

        original_session = await session_manager.get_session(session_id)

    assert result_session == original_session
    assert result_session.rms_session is not None
    assert result_session.rms_session.root == mock_rms_root
    assert result_session.rms_session.project == mock_rms_project


async def test_add_rms_project_to_session_no_project_session(
    session_manager: SessionManager,
    tmp_path_mocked_home: Path,
    mock_rms_root: MagicMock,
    mock_rms_project: MagicMock,
) -> None:
    """Test adding an RMS project when no FMU project is open in session."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    with (
        patch("fmu_settings_api.session.session_manager", session_manager),
        pytest.raises(SessionNotFoundError, match="No FMU project directory open"),
    ):
        await add_rms_project_to_session(session_id, mock_rms_root, mock_rms_project)


async def test_add_rms_project_to_session_closes_existing(
    session_manager: SessionManager,
    tmp_path_mocked_home: Path,
    mock_rms_root: MagicMock,
    mock_rms_project: MagicMock,
) -> None:
    """Test that adding a new RMS project closes the existing one."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    mock_rms_root_existing = MagicMock(_shutdown=MagicMock())
    mock_rms_project_existing = MagicMock(close=MagicMock())

    with patch("fmu_settings_api.session.session_manager", session_manager):
        await add_fmu_project_to_session(session_id, project_fmu_dir)

        session = await session_manager.get_session(session_id)
        assert isinstance(session, ProjectSession)
        session.rms_session = RmsSession(
            mock_rms_root_existing, mock_rms_project_existing
        )

        result_session = await add_rms_project_to_session(
            session_id, mock_rms_root, mock_rms_project
        )

        original_session = await session_manager.get_session(session_id)

    mock_rms_project_existing.close.assert_called_once()
    mock_rms_root_existing._shutdown.assert_called_once()
    assert result_session == original_session
    assert result_session.rms_session is not None
    assert result_session.rms_session.root == mock_rms_root
    assert result_session.rms_session.project == mock_rms_project


async def test_add_fmu_project_to_session_closes_existing_rms(
    session_manager: SessionManager,
    tmp_path_mocked_home: Path,
    mock_rms_root: MagicMock,
    mock_rms_project: MagicMock,
) -> None:
    """Test that switching projects closes any existing RMS project."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project1_path = tmp_path_mocked_home / "test_project1"
    project1_path.mkdir()
    project1_fmu_dir = init_fmu_directory(project1_path)

    project2_path = tmp_path_mocked_home / "test_project2"
    project2_path.mkdir()
    project2_fmu_dir = init_fmu_directory(project2_path)

    with patch("fmu_settings_api.session.session_manager", session_manager):
        await add_fmu_project_to_session(session_id, project1_fmu_dir)

        session = await session_manager.get_session(session_id)
        assert isinstance(session, ProjectSession)
        session.rms_session = RmsSession(mock_rms_root, mock_rms_project)

        project_session = await add_fmu_project_to_session(session_id, project2_fmu_dir)

        original_session = await session_manager.get_session(session_id)

    mock_rms_project.close.assert_called_once()
    mock_rms_root._shutdown.assert_called_once()
    assert project_session == original_session
    assert project_session.project_fmu_directory == project2_fmu_dir
    assert project_session.rms_session is None


async def test_remove_rms_project_from_session_success(
    session_manager: SessionManager,
    tmp_path_mocked_home: Path,
    mock_rms_root: MagicMock,
    mock_rms_project: MagicMock,
) -> None:
    """Test removing an RMS project from a session."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    with patch("fmu_settings_api.session.session_manager", session_manager):
        await add_fmu_project_to_session(session_id, project_fmu_dir)
        await add_rms_project_to_session(session_id, mock_rms_root, mock_rms_project)

    result_session = await remove_rms_project_from_session(session_id)
    original_session = await session_manager.get_session(session_id)

    assert result_session.rms_session is None
    assert isinstance(original_session, ProjectSession)
    assert original_session.rms_session is None


async def test_remove_rms_project_from_session_no_project_session(
    session_manager: SessionManager,
    tmp_path_mocked_home: Path,
) -> None:
    """Test removing an RMS project when no FMU project is open."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    with (
        patch("fmu_settings_api.session.session_manager", session_manager),
        pytest.raises(SessionNotFoundError, match="No FMU project directory open"),
    ):
        await remove_rms_project_from_session(session_id)


async def test_remove_rms_project_from_session_closes_project(
    session_manager: SessionManager,
    tmp_path_mocked_home: Path,
    mock_rms_root: MagicMock,
    mock_rms_project: MagicMock,
) -> None:
    """Test that removing an RMS project calls close() on it."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    with patch("fmu_settings_api.session.session_manager", session_manager):
        await add_fmu_project_to_session(session_id, project_fmu_dir)
        await add_rms_project_to_session(session_id, mock_rms_root, mock_rms_project)

        result_session = await remove_rms_project_from_session(session_id)
        original_session = await session_manager.get_session(session_id)

    mock_rms_project.close.assert_called_once()
    mock_rms_root._shutdown.assert_called_once()
    assert result_session == original_session
    assert result_session.id == session_id


async def test_destroy_session_closes_rms_project(
    session_manager: SessionManager,
    tmp_path_mocked_home: Path,
    mock_rms_root: MagicMock,
    mock_rms_project: MagicMock,
) -> None:
    """Test that destroying a session closes the RMS project."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    with patch("fmu_settings_api.session.session_manager", session_manager):
        await add_fmu_project_to_session(session_id, project_fmu_dir)
        await add_rms_project_to_session(session_id, mock_rms_root, mock_rms_project)

        await session_manager.destroy_session(session_id)

    mock_rms_project.close.assert_called_once()
    mock_rms_root._shutdown.assert_called_once()


async def test_remove_fmu_project_from_session_closes_rms_project(
    session_manager: SessionManager,
    tmp_path_mocked_home: Path,
    mock_rms_root: MagicMock,
    mock_rms_project: MagicMock,
) -> None:
    """Test that closing the FMU project also closes the RMS project."""
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(user_fmu_dir)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    project_fmu_dir = init_fmu_directory(project_path)

    with patch("fmu_settings_api.session.session_manager", session_manager):
        await add_fmu_project_to_session(session_id, project_fmu_dir)
        await add_rms_project_to_session(session_id, mock_rms_root, mock_rms_project)

        await remove_fmu_project_from_session(session_id)

    mock_rms_project.close.assert_called_once()
    mock_rms_root._shutdown.assert_called_once()
