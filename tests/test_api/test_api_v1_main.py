"""Tests the root routes of /api/v1."""

import stat
from pathlib import Path
from unittest.mock import patch

from fastapi import status
from fastapi.testclient import TestClient

from fmu.settings._init import init_fmu_directory
from fmu.settings.resources.config import Config
from fmu_settings_api.__main__ import app
from fmu_settings_api.config import settings

client = TestClient(app)


def test_health_check_unauthorized() -> None:
    """Test the health check endpoint with missing token."""
    response = client.get("/api/v1/health", headers={})
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Not authenticated"}


def test_health_check_invalid_token() -> None:
    """Test the health check endpoint with an invalid token."""
    token = "no" * 32
    response = client.get("/api/v1/health", headers={settings.TOKEN_HEADER_NAME: token})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "Not authorized"}


def test_health_check_valid_token(mock_token: str) -> None:
    """Test the health check endpoint with a valid token."""
    response = client.get(
        "/api/v1/health", headers={settings.TOKEN_HEADER_NAME: mock_token}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}


def test_get_fmu_directory_no_permissions(mock_token: str, tmp_path: Path) -> None:
    """Test 403 returns when lacking permissions to path."""
    path = tmp_path / "foo"
    path.mkdir()
    path.chmod(stat.S_IRUSR)

    response = client.post(
        "/api/v1/fmu",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(path)},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": f"Permission denied accessing .fmu at {path}"}


def test_get_fmu_directory_does_not_exist(mock_token: str) -> None:
    """Test 404 returns when .fmu or directory does not exist."""
    path = "/dev/null"
    response = client.post(
        "/api/v1/fmu",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": path},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": f"No .fmu directory found at {path}"}


def test_get_fmu_directory_is_not_directory(mock_token: str, tmp_path: Path) -> None:
    """Test 409 returns when .fmu exists but is not a directory."""
    path = tmp_path / ".fmu"
    path.touch()

    response = client.post(
        "/api/v1/fmu",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path)},
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {
        "detail": f".fmu exists at {tmp_path} but is not a directory"
    }


def test_get_fmu_directory_raises_other_exceptions(mock_token: str) -> None:
    """Test 500 returns if other exceptions are raised."""
    with patch(
        "fmu_settings_api.v1.main._get_fmu_directory", side_effect=Exception("foo")
    ):
        path = "/dev/null"
        response = client.post(
            "/api/v1/fmu",
            headers={settings.TOKEN_HEADER_NAME: mock_token},
            json={"path": path},
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "foo"}


def test_get_fmu_directory_exists(mock_token: str, tmp_path: Path) -> None:
    """Test 200 and config returns when .fmu exists."""
    fmu_dir = init_fmu_directory(tmp_path)

    response = client.post(
        "/api/v1/fmu",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path)},
    )
    assert response.status_code == status.HTTP_200_OK
    config = Config.model_validate(response.json())
    assert fmu_dir.config.load() == config


def test_init_fmu_directory_no_permissions(mock_token: str, tmp_path: Path) -> None:
    """Test 403 returns when lacking permissions to path."""
    path = tmp_path / "foo"
    path.mkdir()
    path.chmod(stat.S_IRUSR)

    response = client.post(
        "/api/v1/fmu/init",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(path)},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": f"Permission denied creating .fmu at {path}"}


def test_init_fmu_directory_does_not_exist(mock_token: str) -> None:
    """Test 404 returns when directory to initialize .fmu in does not exist."""
    path = "/dev/null/foo"
    response = client.post(
        "/api/v1/fmu/init",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": path},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": f"Path {path} does not exist"}


def test_init_fmu_directory_is_not_directory(mock_token: str, tmp_path: Path) -> None:
    """Test 409 returns when .fmu exists already at a path."""
    path = tmp_path / ".fmu"
    path.mkdir()

    response = client.post(
        "/api/v1/fmu/init",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path)},
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {"detail": f".fmu already exists at {tmp_path}"}


def test_init_fmu_directory_raises_other_exceptions(mock_token: str) -> None:
    """Test 500 returns if other exceptions are raised."""
    with patch(
        "fmu_settings_api.v1.main._init_fmu_directory", side_effect=Exception("foo")
    ):
        path = "/dev/null"
        response = client.post(
            "/api/v1/fmu/init",
            headers={settings.TOKEN_HEADER_NAME: mock_token},
            json={"path": path},
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "foo"}


def test_init_and_get_fmu_directory_succeeds(mock_token: str, tmp_path: Path) -> None:
    """Test 200 and config returns when .fmu exists."""
    init_response = client.post(
        "/api/v1/fmu/init",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path)},
    )
    assert init_response.status_code == status.HTTP_200_OK
    init_config = Config.model_validate(init_response.json())
    assert (tmp_path / ".fmu").exists()
    assert (tmp_path / ".fmu").is_dir()
    assert (tmp_path / ".fmu/config.json").exists()

    get_response = client.post(
        "/api/v1/fmu",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={"path": str(tmp_path)},
    )
    assert get_response.status_code == status.HTTP_200_OK
    get_config = Config.model_validate(get_response.json())
    assert init_config == get_config
