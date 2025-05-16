"""Tests the SessionManager functionality."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fmu.settings._init import init_fmu_directory, init_user_fmu_directory

from fmu_settings_api.config import settings
from fmu_settings_api.session import (
    SessionManager,
    create_fmu_session,
    destroy_fmu_session,
    session_manager,
)


def test_session_manager_init() -> None:
    """Tests initialization of the SessionManager."""
    assert session_manager.storage == SessionManager().storage == {}


async def test_create_session(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests creating a new session."""
    fmu_dir = init_fmu_directory(tmp_path_mocked_home)
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(fmu_dir, user_fmu_dir)
    assert session_id in session_manager.storage
    assert session_manager.storage[session_id].fmu_directory == fmu_dir
    assert len(session_manager.storage) == 1


async def test_create_session_wrapper(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests creating a new session with the wrapper."""
    fmu_dir = init_fmu_directory(tmp_path_mocked_home)
    user_fmu_dir = init_user_fmu_directory()
    with patch("fmu_settings_api.session.session_manager", session_manager):
        session_id = await create_fmu_session(fmu_dir, user_fmu_dir)
    assert session_id in session_manager.storage
    assert session_manager.storage[session_id].fmu_directory == fmu_dir
    assert len(session_manager.storage) == 1


async def test_get_non_existing_session(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests getting an existing session."""
    fmu_dir = init_fmu_directory(tmp_path_mocked_home)
    user_fmu_dir = init_user_fmu_directory()
    await session_manager.create_session(fmu_dir, user_fmu_dir)
    assert await session_manager.get_session("no") is None
    assert len(session_manager.storage) == 1


async def test_get_existing_session(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests getting an existing session."""
    fmu_dir = init_fmu_directory(tmp_path_mocked_home)
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(fmu_dir, user_fmu_dir)
    session = await session_manager.get_session(session_id)
    assert session == session_manager.storage[session_id]
    assert len(session_manager.storage) == 1


async def test_get_existing_session_expiration(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests getting an existing session expires."""
    fmu_dir = init_fmu_directory(tmp_path_mocked_home)
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(fmu_dir, user_fmu_dir)
    orig_session = session_manager.storage[session_id]
    expiration_duration = timedelta(seconds=settings.SESSION_EXPIRE_SECONDS)
    assert orig_session.created_at + expiration_duration == orig_session.expires_at

    # Pretend it expired a second ago.
    orig_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert await session_manager.get_session(session_id) is None
    # It should also be destroyed.
    assert session_id not in session_manager.storage
    assert len(session_manager.storage) == 0


async def test_get_existing_session_updates_last_accessed(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests getting an existing session updates its last accessed."""
    fmu_dir = init_fmu_directory(tmp_path_mocked_home)
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(fmu_dir, user_fmu_dir)
    orig_session = deepcopy(session_manager.storage[session_id])
    session = await session_manager.get_session(session_id)
    assert session is not None
    assert orig_session.last_accessed < session.last_accessed


async def test_destroy_fmu_session(
    session_manager: SessionManager, tmp_path_mocked_home: Path
) -> None:
    """Tests destroying a session."""
    fmu_dir = init_fmu_directory(tmp_path_mocked_home)
    user_fmu_dir = init_user_fmu_directory()
    session_id = await session_manager.create_session(fmu_dir, user_fmu_dir)
    with patch("fmu_settings_api.session.session_manager", session_manager):
        await destroy_fmu_session(session_id)
    assert session_id not in session_manager.storage
    assert len(session_manager.storage) == 0
