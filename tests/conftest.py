"""Root configuration for pytest."""

import json
import stat
from collections.abc import AsyncGenerator, Callable, Generator, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Any, Literal
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from fmu.settings import ProjectFMUDirectory
from fmu.settings._fmu_dir import UserFMUDirectory
from fmu.settings._init import init_fmu_directory, init_user_fmu_directory

from fmu_settings_api.__main__ import app
from fmu_settings_api.config import settings
from fmu_settings_api.deps import get_session
from fmu_settings_api.models.smda import StratigraphicUnit
from fmu_settings_api.session import SessionManager, add_fmu_project_to_session


@pytest.fixture
def create_stratigraphic_unit() -> Callable[..., StratigraphicUnit]:
    """Fixture that returns a helper function to create StratigraphicUnit.

    Returns a callable that creates StratigraphicUnit with minimal required fields.
    """

    def _create_stratigraphic_unit(  # noqa: PLR0913
        identifier: str,
        uuid: UUID | None = None,
        strat_unit_type: str = "formation",
        strat_unit_level: int = 3,
        top: str | None = None,
        base: str | None = None,
        top_age: float = 100.0,
        base_age: float = 150.0,
        strat_unit_parent: str | None = None,
        strat_column_type: Literal[
            "lithostratigraphy",
            "sequence stratigraphy",
            "chronostratigraphy",
            "biostratigraphy",
        ] = "lithostratigraphy",
        color_r: int | None = 255,
        color_g: int | None = 0,
        color_b: int | None = 0,
    ) -> StratigraphicUnit:
        return StratigraphicUnit(
            identifier=identifier,
            uuid=uuid or uuid4(),
            strat_unit_type=strat_unit_type,
            strat_unit_level=strat_unit_level,
            top=top or f"{identifier} Top",
            base=base or f"{identifier} Base",
            top_age=top_age,
            base_age=base_age,
            strat_unit_parent=strat_unit_parent,
            strat_column_type=strat_column_type,
            color_r=color_r,
            color_g=color_g,
            color_b=color_b,
        )

    return _create_stratigraphic_unit


@pytest.fixture(autouse=True)
def reset_dependency_overrides() -> Generator[None, None, None]:
    """Ensure FastAPI dependency overrides do not leak between tests."""
    original_overrides = app.dependency_overrides.copy()
    yield
    app.dependency_overrides = original_overrides


@pytest.fixture
def mock_token() -> str:
    """Sets a token."""
    from fmu_settings_api.config import settings  # noqa: PLC0415

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
        patch("fmu_settings_api.deps.session.session_manager", session_manager),
        patch("fmu_settings_api.session.session_manager", session_manager),
        patch("fmu_settings_api.v1.routes.session.session_manager", session_manager),
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


@pytest.fixture
def smda_masterdata() -> dict[str, Any]:
    """Returns an example SMDA masterdata for the .fmu project."""
    return {
        "stratigraphic_column": {
            "identifier": "DROGON_2020",
            "uuid": "15ce3b84-766f-4c93-9050-b154861f9100",
        },
        "coordinate_system": {
            "identifier": "ST_WGS84_UTM37N_P32637",
            "uuid": "15ce3b84-766f-4c93-9050-b154861f9100",
        },
        "country": [
            {"identifier": "Norway", "uuid": "15ce3b84-766f-4c93-9050-b154861f9100"}
        ],
        "discovery": [
            {
                "short_identifier": "SomeDiscovery",
                "uuid": "15ce3b84-766f-4c93-9050-b154861f9100",
            }
        ],
        "field": [
            {"identifier": "OseFax", "uuid": "15ce3b84-766f-4c93-9050-b154861f9100"}
        ],
    }


@pytest.fixture
def model_data() -> dict[str, Any]:
    """Returns an example model data for the .fmu project."""
    return {
        "name": "Drogon",
        "revision": "21.0.0.dev",
        "description": ["Test model setup", "Used for development"],
    }


@pytest.fixture
def access_data() -> dict[str, Any]:
    """Returns example access data for the .fmu project."""
    return {"asset": {"name": "Drogon"}, "classification": "internal"}


@pytest.fixture
def global_variables_mock() -> dict[str, Any]:
    """Returns an example of the global_variables.yml file with SMDA masterdata."""
    return {
        "masterdata": {
            "smda": {
                "stratigraphic_column": {
                    "identifier": "ALPHA_2024",
                    "uuid": "15ce3b84-766f-4c93-9050-b154861f9100",
                },
                "coordinate_system": {
                    "identifier": "ST_WGS84_UTM37N_P32637",
                    "uuid": "15ce3b84-766f-4c93-9050-b154861f9100",
                },
                "country": [
                    {
                        "identifier": "Norway",
                        "uuid": "15ce3b84-766f-4c93-9050-b154861f9100",
                    }
                ],
                "discovery": [
                    {
                        "short_identifier": "SomeDiscovery",
                        "uuid": "15ce3b84-766f-4c93-9050-b154861f9100",
                    }
                ],
                "field": [
                    {
                        "identifier": "OseFax",
                        "uuid": "15ce3b84-766f-4c93-9050-b154861f9100",
                    }
                ],
            }
        },
        "access": {"asset": {"name": "ValidAsset"}, "classification": "internal"},
        "model": {"name": "ff", "revision": "21.1.0.dev"},
        "stratigraphy": {
            "MSL": {"stratigraphic": False, "name": "MSL"},
            "Seabase": {"stratigraphic": False, "name": "Seabase"},
            "TopAlpha": {"stratigraphic": True, "name": "Alpha Fm. Top"},
        },
        "global": {"GLOBAL_VARS_EXAMPLE": 99, "OTHER": "skipped"},
        "rms": {
            "horizons": {"TOP_RES": ["TopAlpha", "TopBeta", "TopGamma", "BaseAlpha"]},
            "zones": {"ZONE_RES": ["Alpha", "Beta", "Gamma"]},
        },
    }


def _write_global_config_to_path(
    global_config_path: Path, global_config: dict[str, Any]
) -> Path:
    folder_path = global_config_path.parent
    folder_path.mkdir(parents=True, exist_ok=True)
    with open(global_config_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(global_config, indent=2, sort_keys=True))
    return global_config_path


@pytest.fixture
def global_config_default_path(
    global_variables_mock: dict[str, Any], tmp_path: Path
) -> Path:
    """Writes a valid global config to the project default path and returns the path."""
    default_path = tmp_path / Path("fmuconfig/output/global_variables.yml")
    return _write_global_config_to_path(default_path, global_variables_mock)


@pytest.fixture
def global_config_custom_path(
    global_variables_mock: dict[str, Any], tmp_path: Path
) -> Path:
    """Writes a valid global config to a custom path and returns the path."""
    custom_path = tmp_path / Path("custom/fmuconfig/output/custom_file.yml")
    return _write_global_config_to_path(custom_path, global_variables_mock)
