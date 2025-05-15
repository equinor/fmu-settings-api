"""Tests the /api/v1/fmu routes."""

import stat
from pathlib import Path
from unittest.mock import patch

from fastapi import status
from fastapi.testclient import TestClient
from fmu.settings._init import init_fmu_directory
from fmu.settings.models.project_config import ProjectConfig
from pytest import MonkeyPatch

from fmu_settings_api.__main__ import app
from fmu_settings_api.config import settings

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


# GET fmu/ #


def test_get_cwd_fmu_directory_no_permissions(
    mock_token: str, fmu_dir_no_permissions: Path, monkeypatch: MonkeyPatch
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


def test_get_cwd_fmu_directory_does_not_exist(
    mock_token: str, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Test 404 returns when .fmu or directory does not exist from the cwd."""
    ert_model_path = tmp_path / "project/24.0.3/ert/model"
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
    mock_token: str, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Test 404 returns when .fmu exists but is not a directory.

    Although a .fmu file exists, because a .fmu _directory_ is not, it is
    treated as a 404.
    """
    path = tmp_path / ".fmu"
    path.touch()
    ert_model_path = tmp_path / "project/24.0.3/ert/model"
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


def test_get_cwd_fmu_directory_raises_other_exceptions(mock_token: str) -> None:
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
    mock_token: str, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Test 200 and config returns when .fmu exists."""
    fmu_dir = init_fmu_directory(tmp_path)
    ert_model_path = tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    response = client.get(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
    )
    assert response.status_code == status.HTTP_200_OK
    config = ProjectConfig.model_validate(response.json())
    assert fmu_dir.config.load() == config


async def test_get_fmu_directory_sets_session_cookie(
    mock_token: str, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Tests that getting an FMU Directory sets a correct session cookie."""
    fmu_dir = init_fmu_directory(tmp_path)
    ert_model_path = tmp_path / "project/24.0.3/ert/model"
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
    mock_token: str, fmu_dir_no_permissions: Path
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


def test_post_fmu_directory_does_not_exist(mock_token: str) -> None:
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


def test_post_fmu_directory_is_not_directory(mock_token: str, tmp_path: Path) -> None:
    """Test 409 returns when .fmu exists but is not a directory."""
    path = tmp_path / ".fmu"
    path.touch()

    response = client.post(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path)},
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {
        "detail": f".fmu exists at {tmp_path} but is not a directory"
    }
    assert settings.SESSION_COOKIE_KEY not in response.cookies


def test_post_fmu_directory_raises_other_exceptions(mock_token: str) -> None:
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


def test_post_fmu_directory_exists(mock_token: str, tmp_path: Path) -> None:
    """Test 200 and config returns when .fmu exists."""
    fmu_dir = init_fmu_directory(tmp_path)

    response = client.post(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path)},
    )
    assert response.status_code == status.HTTP_200_OK
    config = ProjectConfig.model_validate(response.json())
    assert fmu_dir.config.load() == config


async def test_post_fmu_directory_sets_session_cookie(
    mock_token: str, tmp_path: Path
) -> None:
    """Tests that getting an FMU Directory sets a correct session cookie."""
    fmu_dir = init_fmu_directory(tmp_path)

    response = client.post(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path)},
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
    mock_token: str, tmp_path: Path
) -> None:
    """Tests that deleting a session deletes the session cookie and session."""
    from fmu_settings_api.session import session_manager

    fmu_dir = init_fmu_directory(tmp_path)

    setup_response = client.post(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path)},
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
    assert (
        response.json()["message"]
        == f"FMU directory {fmu_dir.path} closed successfully"
    )
    deleted_session_id = response.cookies.get(settings.SESSION_COOKIE_KEY, None)
    assert deleted_session_id is None

    session = await session_manager.get_session(session_id)
    assert session is None


# POST fmu/init #


def test_post_init_fmu_directory_no_permissions(
    mock_token: str, tmp_path: Path
) -> None:
    """Test 403 returns when lacking permissions to path."""
    path = tmp_path / "foo"
    path.mkdir()
    path.chmod(stat.S_IRUSR)

    response = client.post(
        f"{ROUTE}/init",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(path)},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": f"Permission denied creating .fmu at {path}"}


def test_post_init_fmu_directory_does_not_exist(mock_token: str) -> None:
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
    mock_token: str, tmp_path: Path
) -> None:
    """Test 409 returns when .fmu exists as a file at a path."""
    path = tmp_path / ".fmu"
    path.touch()

    response = client.post(
        f"{ROUTE}/init",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path)},
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {"detail": f".fmu already exists at {tmp_path}"}


def test_post_init_fmu_directory_already_exists(
    mock_token: str, tmp_path: Path
) -> None:
    """Test 409 returns when .fmu exists already at a path."""
    path = tmp_path / ".fmu"
    path.mkdir()

    response = client.post(
        f"{ROUTE}/init",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path)},
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {"detail": f".fmu already exists at {tmp_path}"}


def test_post_init_fmu_directory_raises_other_exceptions(mock_token: str) -> None:
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
    mock_token: str, tmp_path: Path
) -> None:
    """Test 200 and config returns when .fmu exists."""
    init_response = client.post(
        f"{ROUTE}/init",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path)},
    )
    assert init_response.status_code == status.HTTP_200_OK
    init_config = ProjectConfig.model_validate(init_response.json())
    assert (tmp_path / ".fmu").exists()
    assert (tmp_path / ".fmu").is_dir()
    assert (tmp_path / ".fmu/config.json").exists()

    get_response = client.post(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path)},
    )
    assert get_response.status_code == status.HTTP_200_OK
    get_config = ProjectConfig.model_validate(get_response.json())
    assert init_config == get_config


async def test_post_init_succeeds_and_sets_session_cookie(
    mock_token: str, tmp_path: Path
) -> None:
    """Test thats a POST fmu/init succeeds and sets a session cookie."""
    init_response = client.post(
        f"{ROUTE}/init",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path)},
    )
    assert init_response.status_code == status.HTTP_200_OK
    session_id = init_response.cookies.get(settings.SESSION_COOKIE_KEY, None)
    assert session_id is not None

    from fmu_settings_api.session import session_manager

    session = await session_manager.get_session(session_id)
    assert session is not None
    assert session.fmu_directory.path == tmp_path / ".fmu"
