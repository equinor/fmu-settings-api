"""Tests the /api/v1/project routes."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from unittest.mock import patch

from fastapi import status
from fastapi.testclient import TestClient
from fmu.settings._fmu_dir import UserFMUDirectory
from fmu.settings._init import init_fmu_directory
from pytest import MonkeyPatch

from fmu_settings_api.__main__ import app
from fmu_settings_api.config import settings
from fmu_settings_api.models.project import FMUProject
from fmu_settings_api.session import ProjectSession, Session

client = TestClient(app)

ROUTE = "/api/v1/project"


# GET project/ #


def test_get_project_does_not_care_about_token(mock_token: str) -> None:
    """Tests that a header token is irrelevent to the route."""
    response = client.get(ROUTE)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "No active session found"}

    response = client.get(ROUTE, headers={settings.TOKEN_HEADER_NAME: mock_token})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "No active session found"}

    response = client.get(ROUTE, headers={settings.TOKEN_HEADER_NAME: "no" * 32})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "No active session found"}


def test_get_project_no_directory_permissions(
    client_with_session: TestClient,
    session_tmp_path: Path,
    monkeypatch: MonkeyPatch,
    no_permissions: Callable[[str | Path], AbstractContextManager[None]],
) -> None:
    """Test 403 returns when lacking permissions somewhere in the path tree."""
    bad_project_dir = session_tmp_path / ".fmu"
    bad_project_dir.mkdir()

    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    with no_permissions(bad_project_dir):
        response = client_with_session.get(ROUTE)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Permission denied locating .fmu"}


def test_get_project_directory_does_not_exist(
    client_with_session: TestClient, session_tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Test 404 returns when project .fmu cannot be found."""
    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    response = client_with_session.get(ROUTE)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {
        "detail": f"No .fmu directory found from {ert_model_path}"
    }


def test_get_project_directory_is_not_directory(
    client_with_session: TestClient, session_tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Test 404 returns when project .fmu exists but is not a directory.

    Although a .fmu file exists, because a .fmu _directory_ is not, it is
    treated as a 404.
    """
    fmu_dir_path = session_tmp_path / ".fmu"
    fmu_dir_path.touch()
    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    response = client_with_session.get(ROUTE)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {
        "detail": f"No .fmu directory found from {ert_model_path}"
    }


def test_get_project_raises_other_exceptions(client_with_session: TestClient) -> None:
    """Test 500 returns if other exceptions are raised."""
    with patch(
        "fmu_settings_api.v1.routes.project.find_nearest_fmu_directory",
        side_effect=Exception("foo"),
    ):
        response = client_with_session.get(ROUTE)
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "foo"}


def test_get_project_directory_exists(
    client_with_session: TestClient,
    session_tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test 200 and config returns when .fmu exists."""
    existing_fmu_dir = init_fmu_directory(session_tmp_path)

    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    response = client_with_session.get(ROUTE)
    assert response.status_code == status.HTTP_200_OK, response.json()

    fmu_project = FMUProject.model_validate(response.json())
    assert fmu_project.path == session_tmp_path
    assert fmu_project.project_dir_name == session_tmp_path.name
    assert existing_fmu_dir.config.load() == fmu_project.config


async def test_get_project_updates_session(
    client_with_session: TestClient,
    session_tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Tests that getting an project FMU directory updates the user session."""
    existing_fmu_dir = init_fmu_directory(session_tmp_path)

    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    response = client_with_session.get(ROUTE)
    assert response.status_code == status.HTTP_200_OK, response.json()

    session_id = client_with_session.cookies.get(settings.SESSION_COOKIE_KEY, None)
    assert session_id is not None

    from fmu_settings_api.session import session_manager  # noqa PLC0415

    session = await session_manager.get_session(session_id)
    assert session is not None
    assert isinstance(session, ProjectSession)
    assert session.project_fmu_directory.path == session_tmp_path / ".fmu"
    assert existing_fmu_dir.config.load() == session.project_fmu_directory.config.load()


async def test_get_project_already_in_session(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Tests when an .fmu project is already in a session.

    It should just return that project .fmu instance in the session.
    """
    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    response = client_with_project_session.get(ROUTE)
    assert response.status_code == status.HTTP_200_OK, response.json()
    fmu_project = FMUProject.model_validate(response.json())

    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None

    from fmu_settings_api.session import session_manager  # noqa PLC0415

    session = await session_manager.get_session(session_id)
    assert session is not None
    assert isinstance(session, ProjectSession)
    assert session.project_fmu_directory.path == session_tmp_path / ".fmu"
    assert session.project_fmu_directory.config.load() == fmu_project.config


# POST project/ #


def test_post_fmu_directory_no_permissions(
    client_with_session: TestClient,
    session_tmp_path: Path,
    no_permissions: Callable[[str | Path], AbstractContextManager[None]],
) -> None:
    """Test 403 returns when lacking permissions to path."""
    bad_project_dir = session_tmp_path / ".fmu"
    bad_project_dir.mkdir()

    with no_permissions(bad_project_dir):
        response = client_with_session.post(ROUTE, json={"path": str(bad_project_dir)})
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {
        "detail": f"Permission denied accessing .fmu at {bad_project_dir}"
    }


def test_post_fmu_directory_does_not_exist(client_with_session: TestClient) -> None:
    """Test 404 returns when .fmu or directory does not exist."""
    path = "/dev/null"
    response = client_with_session.post(ROUTE, json={"path": path})
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": f"No .fmu directory found at {path}"}


def test_post_fmu_directory_is_not_directory(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 409 returns when .fmu exists but is not a directory."""
    path = session_tmp_path / ".fmu"
    path.touch()

    response = client_with_session.post(ROUTE, json={"path": str(session_tmp_path)})
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {
        "detail": f".fmu exists at {session_tmp_path} but is not a directory"
    }


def test_post_fmu_directory_raises_other_exceptions(
    client_with_session: TestClient,
) -> None:
    """Test 500 returns if other exceptions are raised."""
    with patch(
        "fmu_settings_api.v1.routes.project.get_fmu_directory",
        side_effect=Exception("foo"),
    ):
        path = "/dev/null"
        response = client_with_session.post(ROUTE, json={"path": path})
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "foo"}


async def test_post_fmu_directory_exists(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 200 and config returns when .fmu exists.

    Also checks that the session instance is updated.
    """
    fmu_dir = init_fmu_directory(session_tmp_path)

    response = client_with_session.post(ROUTE, json={"path": str(session_tmp_path)})
    assert response.status_code == status.HTTP_200_OK
    fmu_project = FMUProject.model_validate(response.json())
    assert fmu_project.path == session_tmp_path
    assert fmu_project.project_dir_name == session_tmp_path.name
    assert fmu_dir.config.load() == fmu_project.config

    session_id = client_with_session.cookies.get(settings.SESSION_COOKIE_KEY, None)
    assert session_id is not None

    from fmu_settings_api.session import session_manager  # noqa PLC0415

    session = await session_manager.get_session(session_id)
    assert session is not None
    assert isinstance(session, ProjectSession)
    assert session.project_fmu_directory.path == session_tmp_path / ".fmu"
    assert session.project_fmu_directory.config.load() == fmu_project.config


async def test_post_fmu_directory_changes_session_instance(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Tests that posting a new project changes the instance in the session."""
    project_x = session_tmp_path / "project_x"
    project_x.mkdir()
    x_fmu_dir = init_fmu_directory(project_x)

    project_y = session_tmp_path / "project_y"
    project_y.mkdir()
    y_fmu_dir = init_fmu_directory(project_y)

    # Check Project X
    response = client_with_session.post(ROUTE, json={"path": str(project_x)})
    assert response.status_code == status.HTTP_200_OK, response.json()
    fmu_project = FMUProject.model_validate(response.json())
    assert fmu_project.path == project_x
    assert fmu_project.project_dir_name == project_x.name
    assert x_fmu_dir.config.load() == fmu_project.config

    session_id = client_with_session.cookies.get(settings.SESSION_COOKIE_KEY, None)
    assert session_id is not None

    from fmu_settings_api.session import session_manager  # noqa PLC0415

    session = await session_manager.get_session(session_id)
    assert session is not None
    assert isinstance(session, ProjectSession)
    assert session.project_fmu_directory.path == project_x / ".fmu"
    assert session.project_fmu_directory.config.load() == fmu_project.config

    # Check Project Y
    response = client_with_session.post(ROUTE, json={"path": str(project_y)})
    assert response.status_code == status.HTTP_200_OK, response.json()
    fmu_project = FMUProject.model_validate(response.json())
    assert fmu_project.path == project_y
    assert fmu_project.project_dir_name == project_y.name
    assert y_fmu_dir.config.load() == fmu_project.config

    session = await session_manager.get_session(session_id)
    assert session is not None
    assert isinstance(session, ProjectSession)
    assert session.project_fmu_directory.path == project_y / ".fmu"
    assert session.project_fmu_directory.config.load() == fmu_project.config


# DELETE project/ #


async def test_delete_project_session_requires_session(
    tmp_path_mocked_home: Path,
) -> None:
    """Tests that deleting a project session requires a user session."""
    response = client.delete(ROUTE)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
    assert response.json()["detail"] == "No active session found"


async def test_delete_project_session_requires_project_session(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Tests that deleting a project session requires a user session."""
    response = client_with_session.delete(ROUTE)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
    assert response.json()["detail"] == "No FMU project directory open"


async def test_delete_project_session_returns_to_user_session(
    client_with_project_session: TestClient, session_tmp_path: Path
) -> None:
    """Tests that deleting a project session returns to a user session."""
    from fmu_settings_api.session import session_manager  # noqa PLC0415

    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert session is not None
    assert isinstance(session, ProjectSession)

    response = client_with_project_session.delete(ROUTE)
    assert response.status_code == status.HTTP_200_OK, response.json()
    assert (
        response.json()["message"]
        == f"FMU directory {session.project_fmu_directory.path} closed successfully"
    )
    deleted_session_id = response.cookies.get(settings.SESSION_COOKIE_KEY, None)
    assert deleted_session_id is None

    session = await session_manager.get_session(session_id)
    assert session is not None
    assert isinstance(session, Session)


# POST project/init #


def test_post_init_fmu_directory_no_permissions(
    client_with_session: TestClient,
    session_tmp_path: Path,
    no_permissions: Callable[[str | Path], AbstractContextManager[None]],
) -> None:
    """Test 403 returns when lacking permissions to path."""
    path = session_tmp_path / "foo"
    path.mkdir()

    with no_permissions(path):
        response = client_with_session.post(f"{ROUTE}/init", json={"path": str(path)})
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": f"Permission denied creating .fmu at {path}"}


def test_post_init_fmu_directory_does_not_exist(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 404 returns when directory to initialize .fmu does not exist."""
    path = "/dev/null/foo"
    response = client_with_session.post(f"{ROUTE}/init", json={"path": path})
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": f"Path {path} does not exist"}


def test_post_init_fmu_directory_is_not_a_directory(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 409 returns when .fmu exists as a file at a path."""
    path = session_tmp_path / ".fmu"
    path.touch()

    response = client_with_session.post(
        f"{ROUTE}/init", json={"path": str(session_tmp_path)}
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {"detail": f".fmu already exists at {session_tmp_path}"}


def test_post_init_fmu_directory_already_exists(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 409 returns when .fmu exists already at a path."""
    path = session_tmp_path / ".fmu"
    path.mkdir()

    response = client_with_session.post(
        f"{ROUTE}/init", json={"path": str(session_tmp_path)}
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {"detail": f".fmu already exists at {session_tmp_path}"}


def test_post_init_fmu_directory_raises_other_exceptions(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 500 returns if other exceptions are raised."""
    with patch(
        "fmu_settings_api.v1.routes.project.init_fmu_directory",
        side_effect=Exception("foo"),
    ):
        path = "/dev/null"
        response = client_with_session.post(f"{ROUTE}/init", json={"path": path})
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "foo"}


def test_post_init_and_get_fmu_directory_succeeds(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 200 and config returns when .fmu exists."""
    tmp_path = session_tmp_path
    init_response = client_with_session.post(
        f"{ROUTE}/init", json={"path": str(tmp_path)}
    )
    assert init_response.status_code == status.HTTP_200_OK
    init_fmu_project = FMUProject.model_validate(init_response.json())
    assert init_fmu_project.path == tmp_path
    assert init_fmu_project.project_dir_name == tmp_path.name

    assert (tmp_path / ".fmu").exists()
    assert (tmp_path / ".fmu").is_dir()
    assert (tmp_path / ".fmu/config.json").exists()

    get_response = client_with_session.post(ROUTE, json={"path": str(tmp_path)})
    assert get_response.status_code == status.HTTP_200_OK
    get_fmu_project = FMUProject.model_validate(get_response.json())
    assert init_fmu_project == get_fmu_project


async def test_post_init_updates_session_instance(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test thats a POST fmu/init succeeds and sets a session cookie."""
    init_response = client_with_session.post(
        f"{ROUTE}/init", json={"path": str(session_tmp_path)}
    )
    assert init_response.status_code == status.HTTP_200_OK
    session_id = client_with_session.cookies.get(settings.SESSION_COOKIE_KEY, None)
    assert session_id is not None

    from fmu_settings_api.session import session_manager  # noqa PLC0415

    session = await session_manager.get_session(session_id)
    assert session is not None
    assert isinstance(session, ProjectSession)
    assert session.project_fmu_directory.path == session_tmp_path / ".fmu"
    assert session.user_fmu_directory.path == UserFMUDirectory().path
