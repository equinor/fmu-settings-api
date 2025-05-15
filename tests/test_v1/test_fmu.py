"""Tests the /api/v1/fmu routes."""

import json
import stat
from pathlib import Path
from unittest.mock import patch

from fastapi import status
from fastapi.testclient import TestClient
from fmu.settings._fmu_dir import UserFMUDirectory
from fmu.settings._init import init_fmu_directory, init_user_fmu_directory
from fmu.settings.models.user_config import UserConfig
from pytest import MonkeyPatch

from fmu_settings_api.__main__ import app
from fmu_settings_api.config import settings
from fmu_settings_api.models.fmu import FMUProject

client = TestClient(app)

ROUTE = "/api/v1/fmu"


def test_get_fmu_unauthorized() -> None:
    """Tests the fmu routes requires a token."""
    response = client.post(ROUTE, headers={})
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Not authenticated"}


def test_get_fmu_invalid_token() -> None:
    """Tests the fmu routes requires a valid token."""
    token = "no" * 32
    response = client.post(ROUTE, headers={settings.TOKEN_HEADER_NAME: token})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "Not authorized"}


def test_get_fmu_unauthorized_does_not_create_user_fmu(
    tmp_path_mocked_home: Path,
) -> None:
    """Tests unauthenticated requests do not create a user .fmu."""
    response = client.get(ROUTE, headers={})
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Not authenticated"}
    assert not (tmp_path_mocked_home / "home/.fmu").exists()


# User FMU Directory dependency errors #


def test_create_user_fmu_no_permissions(
    user_fmu_dir_no_permissions: Path, mock_token: str, monkeypatch: MonkeyPatch
) -> None:
    """Tests that user .fmu directory permissions errors return a 403."""
    monkeypatch.chdir(user_fmu_dir_no_permissions)
    response = client.get(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Permission denied creating user .fmu"}


def test_create_user_fmu_exists_as_a_file(
    tmp_path_mocked_home: Path, mock_token: str, monkeypatch: MonkeyPatch
) -> None:
    """Tests that a user .fmu as a file raises a 409."""
    (tmp_path_mocked_home / "home/.fmu").touch()
    monkeypatch.chdir(tmp_path_mocked_home)
    response = client.get(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {
        "detail": "User .fmu already exists but is invalid (i.e. is not a directory)"
    }


def test_create_user_unknown_failure(
    tmp_path_mocked_home: Path, mock_token: str, monkeypatch: MonkeyPatch
) -> None:
    """Tests that an unknown exception returns 500."""
    with patch(
        "fmu_settings_api.deps.init_user_fmu_directory",
        side_effect=Exception("foo"),
    ):
        user_fmu_path = tmp_path_mocked_home / "home/.fmu"
        assert not user_fmu_path.exists()

        monkeypatch.chdir(tmp_path_mocked_home)
        init_fmu_directory(tmp_path_mocked_home)
        response = client.get(
            ROUTE,
            headers={settings.TOKEN_HEADER_NAME: mock_token},
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


# GET fmu/ #


def test_get_cwd_fmu_directory_no_permissions(
    fmu_dir_no_permissions: Path, mock_token: str, monkeypatch: MonkeyPatch
) -> None:
    """Test 403 returns when lacking permissions somewhere in the path tree."""
    ert_model_path = fmu_dir_no_permissions / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)
    response = client.get(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Permission denied locating .fmu"}


def test_get_cwd_fmu_directory_no_permissions_creates_user_fmu(
    fmu_dir_no_permissions: Path, mock_token: str, monkeypatch: MonkeyPatch
) -> None:
    """Tests an authenticated but erroroneous requests still creates a user .fmu."""
    ert_model_path = fmu_dir_no_permissions / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)
    response = client.get(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Permission denied locating .fmu"}

    user_fmu_path = fmu_dir_no_permissions / "home/.fmu"
    assert user_fmu_path.exists()
    assert user_fmu_path.is_dir()
    assert user_fmu_path == UserFMUDirectory().path


def test_get_cwd_fmu_directory_does_not_exist(
    tmp_path_mocked_home: Path, mock_token: str, monkeypatch: MonkeyPatch
) -> None:
    """Test 404 returns when .fmu or directory does not exist from the cwd."""
    ert_model_path = tmp_path_mocked_home / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)
    response = client.get(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {
        "detail": f"No .fmu directory found from {ert_model_path}"
    }


def test_get_cwd_fmu_directory_is_not_directory(
    tmp_path_mocked_home: Path, mock_token: str, monkeypatch: MonkeyPatch
) -> None:
    """Test 404 returns when .fmu exists but is not a directory.

    Although a .fmu file exists, because a .fmu _directory_ is not, it is
    treated as a 404.
    """
    path = tmp_path_mocked_home / ".fmu"
    path.touch()
    ert_model_path = tmp_path_mocked_home / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    response = client.get(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {
        "detail": f"No .fmu directory found from {ert_model_path}"
    }


def test_get_cwd_fmu_directory_raises_other_exceptions(
    tmp_path_mocked_home: Path, mock_token: str
) -> None:
    """Test 500 returns if other exceptions are raised."""
    with patch(
        "fmu_settings_api.v1.routes.fmu.find_nearest_fmu_directory",
        side_effect=Exception("foo"),
    ):
        response = client.get(
            ROUTE,
            headers={settings.TOKEN_HEADER_NAME: mock_token},
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "foo"}


def test_get_cwd_fmu_directory_exists(
    tmp_path_mocked_home: Path, mock_token: str, monkeypatch: MonkeyPatch
) -> None:
    """Test 200 and config returns when .fmu exists."""
    fmu_dir = init_fmu_directory(tmp_path_mocked_home)
    ert_model_path = tmp_path_mocked_home / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    response = client.get(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
    )
    assert response.status_code == status.HTTP_200_OK
    fmu_project = FMUProject.model_validate(response.json())
    assert fmu_project.path == tmp_path_mocked_home
    assert fmu_project.project_dir_name == tmp_path_mocked_home.name
    assert fmu_dir.config.load() == fmu_project.config


def test_get_cwd_fmu_directory_creates_user_fmu_if_not_there(
    tmp_path_mocked_home: Path, mock_token: str, monkeypatch: MonkeyPatch
) -> None:
    """Tests that a user .fmu directory is created as a side effect."""
    user_fmu_path = tmp_path_mocked_home / "home/.fmu"
    assert not user_fmu_path.exists()

    monkeypatch.chdir(tmp_path_mocked_home)
    init_fmu_directory(tmp_path_mocked_home)
    response = client.get(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
    )
    assert response.status_code == status.HTTP_200_OK

    assert user_fmu_path.exists()
    assert user_fmu_path.is_dir()
    assert (user_fmu_path / "config.json").exists()

    user_fmu_dir = UserFMUDirectory()
    assert user_fmu_dir.path == user_fmu_path
    # Ensure pass isn't a false positive against a non-mocked .fmu dir by validating
    # timestamps
    with open(user_fmu_path / "config.json", encoding="utf-8") as f:
        user_fmu_config = json.loads(f.read())
    assert user_fmu_dir.config.load() == UserConfig.model_validate(user_fmu_config)


def test_get_cwd_fmu_directory_does_not_error_if_user_fmu_exists(
    tmp_path_mocked_home: Path, mock_token: str, monkeypatch: MonkeyPatch
) -> None:
    """Tests that a user .fmu directory already exists causes no issues."""
    user_fmu_path = tmp_path_mocked_home / "home/.fmu"
    assert not user_fmu_path.exists()
    user_fmu_dir = init_user_fmu_directory()
    assert user_fmu_path.exists()
    assert user_fmu_path.is_dir()
    assert user_fmu_path == user_fmu_dir.path

    monkeypatch.chdir(tmp_path_mocked_home)
    init_fmu_directory(tmp_path_mocked_home)
    response = client.get(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
    )
    assert response.status_code == status.HTTP_200_OK

    assert user_fmu_dir.config.load() == UserFMUDirectory().config.load()


async def test_get_fmu_directory_sets_session_cookie(
    tmp_path_mocked_home: Path, mock_token: str, monkeypatch: MonkeyPatch
) -> None:
    """Tests that getting an FMU Directory sets a correct session cookie."""
    fmu_dir = init_fmu_directory(tmp_path_mocked_home)
    ert_model_path = tmp_path_mocked_home / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    response = client.get(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
    )
    assert response.status_code == status.HTTP_200_OK
    session_id = response.cookies.get(settings.SESSION_COOKIE_KEY, None)
    assert session_id is not None

    from fmu_settings_api.session import session_manager

    session = await session_manager.get_session(session_id)
    assert session is not None
    assert session.fmu_directory.path == fmu_dir.path


# POST fmu/ #


def test_post_fmu_directory_no_permissions(
    fmu_dir_no_permissions: Path, mock_token: str
) -> None:
    """Test 403 returns when lacking permissions to path."""
    response = client.post(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(fmu_dir_no_permissions)},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {
        "detail": f"Permission denied accessing .fmu at {fmu_dir_no_permissions}"
    }
    assert settings.SESSION_COOKIE_KEY not in response.cookies


def test_post_fmu_directory_does_not_exist(
    tmp_path_mocked_home: Path, mock_token: str
) -> None:
    """Test 404 returns when .fmu or directory does not exist."""
    path = "/dev/null"
    response = client.post(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": path},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": f"No .fmu directory found at {path}"}
    assert settings.SESSION_COOKIE_KEY not in response.cookies


def test_post_fmu_directory_is_not_directory(
    tmp_path_mocked_home: Path, mock_token: str
) -> None:
    """Test 409 returns when .fmu exists but is not a directory."""
    path = tmp_path_mocked_home / ".fmu"
    path.touch()

    response = client.post(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path_mocked_home)},
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {
        "detail": f".fmu exists at {tmp_path_mocked_home} but is not a directory"
    }
    assert settings.SESSION_COOKIE_KEY not in response.cookies


def test_post_fmu_directory_raises_other_exceptions(
    tmp_path_mocked_home: Path, mock_token: str
) -> None:
    """Test 500 returns if other exceptions are raised."""
    with patch(
        "fmu_settings_api.v1.routes.fmu.get_fmu_directory", side_effect=Exception("foo")
    ):
        path = "/dev/null"
        response = client.post(
            ROUTE,
            headers={settings.TOKEN_HEADER_NAME: mock_token},
            json={"path": path},
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "foo"}
        assert settings.SESSION_COOKIE_KEY not in response.cookies


def test_post_fmu_directory_exists(tmp_path_mocked_home: Path, mock_token: str) -> None:
    """Test 200 and config returns when .fmu exists."""
    fmu_dir = init_fmu_directory(tmp_path_mocked_home)

    response = client.post(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path_mocked_home)},
    )
    assert response.status_code == status.HTTP_200_OK
    fmu_project = FMUProject.model_validate(response.json())
    assert fmu_project.path == tmp_path_mocked_home
    assert fmu_project.project_dir_name == tmp_path_mocked_home.name
    assert fmu_dir.config.load() == fmu_project.config


def test_post_fmu_directory_creates_user_fmu_if_not_there(
    tmp_path_mocked_home: Path, mock_token: str, monkeypatch: MonkeyPatch
) -> None:
    """Tests that a user .fmu directory is created as a side effect."""
    user_fmu_path = tmp_path_mocked_home / "home/.fmu"
    assert not user_fmu_path.exists()

    init_fmu_directory(tmp_path_mocked_home)
    response = client.post(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path_mocked_home)},
    )
    assert response.status_code == status.HTTP_200_OK

    assert user_fmu_path.exists()
    assert user_fmu_path.is_dir()
    assert (user_fmu_path / "config.json").exists()

    user_fmu_dir = UserFMUDirectory()
    assert user_fmu_dir.path == user_fmu_path
    # Ensure pass isn't a false positive against a non-mocked .fmu dir by validating
    # timestamps
    with open(user_fmu_path / "config.json", encoding="utf-8") as f:
        user_fmu_config = json.loads(f.read())
    assert user_fmu_dir.config.load() == UserConfig.model_validate(user_fmu_config)


def test_post_fmu_directory_does_not_error_if_user_fmu_exists(
    tmp_path_mocked_home: Path, mock_token: str, monkeypatch: MonkeyPatch
) -> None:
    """Tests that a user .fmu directory already exists causes no issues."""
    user_fmu_path = tmp_path_mocked_home / "home/.fmu"
    assert not user_fmu_path.exists()
    user_fmu_dir = init_user_fmu_directory()
    assert user_fmu_path.exists()
    assert user_fmu_path.is_dir()
    assert user_fmu_path == user_fmu_dir.path

    init_fmu_directory(tmp_path_mocked_home)
    response = client.post(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path_mocked_home)},
    )
    assert response.status_code == status.HTTP_200_OK

    assert user_fmu_dir.config.load() == UserFMUDirectory().config.load()


async def test_post_fmu_directory_sets_session_cookie(
    tmp_path_mocked_home: Path, mock_token: str
) -> None:
    """Tests that getting an FMU Directory sets a correct session cookie."""
    fmu_dir = init_fmu_directory(tmp_path_mocked_home)

    response = client.post(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path_mocked_home)},
    )
    assert response.status_code == status.HTTP_200_OK
    session_id = response.cookies.get(settings.SESSION_COOKIE_KEY, None)
    assert session_id is not None

    from fmu_settings_api.session import session_manager

    session = await session_manager.get_session(session_id)
    assert session is not None
    assert session.fmu_directory.path == fmu_dir.path


# DELETE fmu/ #


async def test_delete_fmu_directory_deletes_session_cookie(
    tmp_path_mocked_home: Path, mock_token: str
) -> None:
    """Tests that deleting a session deletes the session cookie and session."""
    from fmu_settings_api.session import session_manager

    fmu_dir = init_fmu_directory(tmp_path_mocked_home)

    setup_response = client.post(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path_mocked_home)},
    )
    assert setup_response.status_code == status.HTTP_200_OK
    session_id = setup_response.cookies.get(settings.SESSION_COOKIE_KEY, None)
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert session is not None
    assert session.fmu_directory.path == fmu_dir.path

    # Actual test below

    response = client.delete(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
    )
    assert response.status_code == status.HTTP_200_OK
    assert (
        response.json()["message"]
        == f"FMU directory {fmu_dir.path} closed successfully"
    )
    deleted_session_id = response.cookies.get(settings.SESSION_COOKIE_KEY, None)
    assert deleted_session_id is None

    session = await session_manager.get_session(session_id)
    assert session is None


def test_delete_fmu_directory_does_not_create_user_fmu(
    tmp_path_mocked_home: Path, mock_token: str, client_with_session: TestClient
) -> None:
    """Tests deleting a .fmu session does not create a user .fmu directory.

    It does not really matter if it does, but it is unexpected behavior if it does.
    """
    assert not (tmp_path_mocked_home / "home/.fmu").exists()
    response = client_with_session.delete(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
    )
    assert response.status_code == status.HTTP_200_OK
    assert not (tmp_path_mocked_home / "home/.fmu").exists()


# POST fmu/init #


def test_post_init_fmu_directory_no_permissions(
    tmp_path_mocked_home: Path, mock_token: str
) -> None:
    """Test 403 returns when lacking permissions to path."""
    path = tmp_path_mocked_home / "foo"
    path.mkdir()
    path.chmod(stat.S_IRUSR)

    response = client.post(
        f"{ROUTE}/init",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(path)},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": f"Permission denied creating .fmu at {path}"}


def test_post_init_fmu_directory_does_not_exist(
    tmp_path_mocked_home: Path, mock_token: str
) -> None:
    """Test 404 returns when directory to initialize .fmu does not exist."""
    path = "/dev/null/foo"
    response = client.post(
        f"{ROUTE}/init",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": path},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": f"Path {path} does not exist"}


def test_post_init_fmu_directory_is_not_a_directory(
    tmp_path_mocked_home: Path, mock_token: str
) -> None:
    """Test 409 returns when .fmu exists as a file at a path."""
    path = tmp_path_mocked_home / ".fmu"
    path.touch()

    response = client.post(
        f"{ROUTE}/init",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path_mocked_home)},
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {
        "detail": f".fmu already exists at {tmp_path_mocked_home}"
    }


def test_post_init_fmu_directory_already_exists(
    tmp_path_mocked_home: Path, mock_token: str
) -> None:
    """Test 409 returns when .fmu exists already at a path."""
    path = tmp_path_mocked_home / ".fmu"
    path.mkdir()

    response = client.post(
        f"{ROUTE}/init",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path_mocked_home)},
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {
        "detail": f".fmu already exists at {tmp_path_mocked_home}"
    }


def test_post_init_fmu_directory_raises_other_exceptions(
    tmp_path_mocked_home: Path, mock_token: str
) -> None:
    """Test 500 returns if other exceptions are raised."""
    with patch(
        "fmu_settings_api.v1.routes.fmu.init_fmu_directory",
        side_effect=Exception("foo"),
    ):
        path = "/dev/null"
        response = client.post(
            f"{ROUTE}/init",
            headers={settings.TOKEN_HEADER_NAME: mock_token},
            json={"path": path},
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "foo"}


def test_post_init_and_get_fmu_directory_succeeds(
    tmp_path_mocked_home: Path, mock_token: str
) -> None:
    """Test 200 and config returns when .fmu exists."""
    tmp_path = tmp_path_mocked_home
    init_response = client.post(
        f"{ROUTE}/init",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path)},
    )
    assert init_response.status_code == status.HTTP_200_OK
    init_fmu_project = FMUProject.model_validate(init_response.json())
    assert init_fmu_project.path == tmp_path
    assert init_fmu_project.project_dir_name == tmp_path.name

    assert (tmp_path / ".fmu").exists()
    assert (tmp_path / ".fmu").is_dir()
    assert (tmp_path / ".fmu/config.json").exists()

    get_response = client.post(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path)},
    )
    assert get_response.status_code == status.HTTP_200_OK
    get_fmu_project = FMUProject.model_validate(get_response.json())
    assert init_fmu_project == get_fmu_project


def test_post_init_and_get_fmu_directory_creates_user_fmu_if_not_there(
    tmp_path_mocked_home: Path, mock_token: str, monkeypatch: MonkeyPatch
) -> None:
    """Tests that a user .fmu directory is created as a side effect."""
    user_fmu_path = tmp_path_mocked_home / "home/.fmu"
    assert not user_fmu_path.exists()

    tmp_path = tmp_path_mocked_home
    init_response = client.post(
        f"{ROUTE}/init",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path)},
    )
    assert init_response.status_code == status.HTTP_200_OK

    user_fmu_dir = UserFMUDirectory()
    assert user_fmu_dir.path == user_fmu_path
    # Ensure pass isn't a false positive against a non-mocked .fmu dir by validating
    # timestamps
    with open(user_fmu_path / "config.json", encoding="utf-8") as f:
        user_fmu_config = json.loads(f.read())
    assert user_fmu_dir.config.load() == UserConfig.model_validate(user_fmu_config)

    get_response = client.post(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path)},
    )
    assert get_response.status_code == status.HTTP_200_OK

    user_fmu_dir = UserFMUDirectory()
    assert user_fmu_dir.path == user_fmu_path
    assert user_fmu_dir.config.load() == UserConfig.model_validate(user_fmu_config)


def test_post_init_and_get_fmu_directory_does_not_error_if_user_fmu_exists(
    tmp_path_mocked_home: Path, mock_token: str, monkeypatch: MonkeyPatch
) -> None:
    """Tests that a user .fmu directory already exists causes no issues."""
    user_fmu_path = tmp_path_mocked_home / "home/.fmu"
    assert not user_fmu_path.exists()
    user_fmu_dir = init_user_fmu_directory()
    assert user_fmu_path.exists()
    assert user_fmu_path.is_dir()
    assert user_fmu_path == user_fmu_dir.path

    tmp_path = tmp_path_mocked_home
    init_response = client.post(
        f"{ROUTE}/init",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path)},
    )
    assert init_response.status_code == status.HTTP_200_OK

    assert user_fmu_dir.config.load() == UserFMUDirectory().config.load()

    get_response = client.post(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path)},
    )
    assert get_response.status_code == status.HTTP_200_OK

    user_fmu_dir = UserFMUDirectory()
    assert user_fmu_dir.path == user_fmu_path
    assert user_fmu_dir.config.load() == UserFMUDirectory().config.load()


async def test_post_init_succeeds_and_sets_session_cookie(
    tmp_path_mocked_home: Path, mock_token: str
) -> None:
    """Test thats a POST fmu/init succeeds and sets a session cookie."""
    init_response = client.post(
        f"{ROUTE}/init",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path_mocked_home)},
    )
    assert init_response.status_code == status.HTTP_200_OK
    session_id = init_response.cookies.get(settings.SESSION_COOKIE_KEY, None)
    assert session_id is not None

    from fmu_settings_api.session import session_manager

    session = await session_manager.get_session(session_id)
    assert session is not None
    assert session.fmu_directory.path == tmp_path_mocked_home / ".fmu"
