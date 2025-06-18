"""Root configuration for pytest."""

import stat
from collections.abc import AsyncGenerator, Callable, Generator, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from fmu.settings import ProjectFMUDirectory
from fmu.settings._fmu_dir import UserFMUDirectory
from fmu.settings._init import init_fmu_directory, init_user_fmu_directory

from fmu_settings_api.__main__ import app
from fmu_settings_api.config import settings
from fmu_settings_api.deps import get_session
from fmu_settings_api.session import SessionManager, add_fmu_project_to_session


@pytest.fixture
def mock_token() -> str:
    """Sets a token."""
    from fmu_settings_api.config import settings  # noqa PLC0415

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
def no_permissions() -> Callable[[str | Path], AbstractContextManager[None]]:
    """Returns a context manager to remove permissions on a file or directory."""

    @contextmanager
    def ctx_manager(filepath: str | Path) -> Iterator[None]:
        """Removes user permissions on path."""
        filepath = Path(filepath)
        filepath.chmod(stat.S_IRUSR)
        yield
        filepath.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

    return ctx_manager


@pytest.fixture
def user_fmu_dir_no_permissions(fmu_dir_path: Path) -> Generator[Path]:
    """Mocks a user .fmu tmp_path without permissions."""
    mocked_user_home = fmu_dir_path / "home"
    mocked_user_home.mkdir()

    with patch("pathlib.Path.home", return_value=mocked_user_home):
        user_fmu_dir = init_user_fmu_directory()
        user_fmu_dir.base_path.chmod(stat.S_IRUSR)
        yield fmu_dir_path
    user_fmu_dir.base_path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)


@pytest.fixture
def tmp_path_mocked_home(tmp_path: Path) -> Generator[Path]:
    """Mocks Path.home() for routes that depend on UserFMUDirectory.

    This mocks the user .fmu into tmp_path/home/.fmu.

    Returns:
        The base tmp_path.
    """
    mocked_user_home = tmp_path / "home"
    mocked_user_home.mkdir()
    with patch("pathlib.Path.home", return_value=mocked_user_home):
        yield tmp_path


@pytest.fixture
def session_manager() -> Generator[SessionManager]:
    """Mocks the session manager and returns its replacement."""
    session_manager = SessionManager()
    with (
        patch("fmu_settings_api.deps.session_manager", session_manager),
        patch("fmu_settings_api.session.session_manager", session_manager),
    ):
        yield session_manager


@pytest.fixture
async def session_id(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> str:
    """Mocks a valid user .fmu session."""
    user_fmu_dir = init_user_fmu_directory()
    return await session_manager.create_session(user_fmu_dir)


@pytest.fixture
async def client_with_session(session_id: str) -> AsyncGenerator[TestClient]:
    """Returns a test client with a valid session."""
    with TestClient(app) as c:
        c.cookies[settings.SESSION_COOKIE_KEY] = session_id
        yield c


@pytest.fixture
async def client_with_project_session(session_id: str) -> AsyncGenerator[TestClient]:
    """Returns a test client with a valid session."""
    session = await get_session(session_id)

    path = session.user_fmu_directory.path.parent.parent  # tmp_path
    fmu_dir = init_fmu_directory(path)
    _ = await add_fmu_project_to_session(session_id, fmu_dir)

    with TestClient(app) as c:
        c.cookies[settings.SESSION_COOKIE_KEY] = session_id
        yield c


@pytest.fixture
async def client_with_smda_session(session_id: str) -> AsyncGenerator[TestClient]:
    """Returns a test client with a valid session."""
    session = await get_session(session_id)

    path = session.user_fmu_directory.path.parent.parent  # tmp_path
    fmu_dir = init_fmu_directory(path)
    _ = await add_fmu_project_to_session(session_id, fmu_dir)

    with TestClient(app) as c:
        c.cookies[settings.SESSION_COOKIE_KEY] = session_id
        c.patch(
            "/api/v1/user/api_key", json={"id": "smda_subscription", "key": "secret"}
        )
        c.patch(
            "/api/v1/session/access_token", json={"id": "smda_api", "key": "secret"}
        )
        yield c


@pytest.fixture
def session_tmp_path() -> Path:
    """Returns the tmp_path equivalent from a mocked user .fmu dir."""
    return UserFMUDirectory().path.parent.parent
