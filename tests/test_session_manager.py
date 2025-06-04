"""Tests the SessionManager functionality."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fmu.settings._init import init_user_fmu_directory
from pydantic import SecretStr

from fmu_settings_api.config import settings
from fmu_settings_api.models.common import AccessToken
from fmu_settings_api.session import (
    SessionManager,
    SessionNotFoundError,
    add_access_token_to_session,
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
