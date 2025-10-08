"""Tests the SessionManager functionality."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fmu.settings._init import init_fmu_directory, init_user_fmu_directory
from fmu.settings._resources.lock_manager import LockError
from pydantic import SecretStr

from fmu_settings_api.config import settings
from fmu_settings_api.models.common import AccessToken
from fmu_settings_api.session import (
    Session,
    SessionManager,
    SessionNotFoundError,
    add_access_token_to_session,
    add_fmu_project_to_session,
    create_fmu_session,
    destroy_fmu_session,
    remove_fmu_project_from_session,
    session_manager,
)


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
