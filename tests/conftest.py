"""Root configuration for pytest."""

import stat
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from fmu.settings import ProjectFMUDirectory
from fmu.settings._init import init_fmu_directory

from fmu_settings_api.__main__ import app
from fmu_settings_api.config import settings
from fmu_settings_api.session import SessionManager


@pytest.fixture
def mock_token() -> str:
    """Sets a token."""
    from fmu_settings_api.config import settings

    token = "safe" * 16
    settings.TOKEN = token
    return token


@pytest.fixture
def fmu_dir(tmp_path: Path) -> ProjectFMUDirectory:
    """Creates a .fmu directory in a tmp path."""
    return init_fmu_directory(tmp_path)


@pytest.fixture
def fmu_dir_path(fmu_dir: ProjectFMUDirectory) -> Path:
    """Returns the tmp path of a .fmu directory."""
    return fmu_dir.base_path


@pytest.fixture
def fmu_dir_no_permissions(fmu_dir_path: Path) -> Generator[Path, None, None]:
    """Mocks a .fmu in a tmp_path without permissions."""
    (fmu_dir_path / ".fmu").chmod(stat.S_IRUSR)
    yield fmu_dir_path
    (fmu_dir_path / ".fmu").chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)


@pytest.fixture
def session_manager() -> Generator[SessionManager]:
    """Mocks the session manager and returns its replacement."""
    session_manager = SessionManager()
    with patch("fmu_settings_api.deps.session_manager", session_manager):
        yield session_manager


@pytest.fixture
async def session_id(tmp_path: Path, session_manager: SessionManager) -> str:
    """Mocks a valid opened .fmu session."""
    fmu_dir = init_fmu_directory(tmp_path)
    return await session_manager.create_session(fmu_dir)


@pytest.fixture
async def client_with_session(session_id: str) -> AsyncGenerator[TestClient]:
    """Returns a test client with a valid session."""
    with TestClient(app) as c:
        c.cookies[settings.SESSION_COOKIE_KEY] = session_id
        yield c
