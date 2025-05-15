"""Tests the /api/v1/config routes."""

import stat
from unittest.mock import patch

from fastapi import status
from fastapi.testclient import TestClient
from fmu.settings.models.project_config import ProjectConfig
from fmu.settings.resources.config_managers import ProjectConfigManager

from fmu_settings_api.__main__ import app
from fmu_settings_api.config import settings
from fmu_settings_api.deps import get_fmu_session

client = TestClient(app)

ROUTE = "/api/v1/config"


def test_get_config_unauthorized() -> None:
    """Test that the config routes requires an auth token."""
    response = client.get(ROUTE, headers={})
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Not authenticated"}


def test_get_config_invalid_token() -> None:
    """Tests the config routes requires a valid token."""
    token = "no" * 32
    response = client.get(ROUTE, headers={settings.TOKEN_HEADER_NAME: token})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "Not authorized"}


def test_get_config_no_session(mock_token: str) -> None:
    """Tests the config routes requires a session."""
    response = client.get(ROUTE, headers={settings.TOKEN_HEADER_NAME: mock_token})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "No active session found"}


async def test_get_config_with_session(
    mock_token: str, client_with_session: TestClient
) -> None:
    """Tests the config is return with a valid session."""
    response = client_with_session.get(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
    )
    assert response.status_code == status.HTTP_200_OK
    assert ProjectConfig.model_validate(response.json())


async def test_get_config_with_session_without_permissions(
    mock_token: str, client_with_session: TestClient
) -> None:
    """Tests the config is return with a valid session, but no config."""
    cookie_session_id = client_with_session.cookies.get(settings.SESSION_COOKIE_KEY)
    assert cookie_session_id is not None
    session = await get_fmu_session(cookie_session_id)

    # Clear the cache first.
    session.fmu_directory.config._cache = None
    fmu_path = session.fmu_directory.path
    fmu_path.chmod(stat.S_IRUSR)

    config_path = session.fmu_directory.config.path

    response = client_with_session.get(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {
        "detail": f"Permission denied loading .fmu config at {config_path}"
    }


async def test_get_config_with_session_but_config_not_found(
    mock_token: str, client_with_session: TestClient
) -> None:
    """Tests the config is return with a valid session, but no config."""
    cookie_session_id = client_with_session.cookies.get(settings.SESSION_COOKIE_KEY)
    assert cookie_session_id is not None
    session = await get_fmu_session(cookie_session_id)

    # Pretend the config/config cache doesn't exist
    session.fmu_directory.config._cache = None
    config_path = session.fmu_directory.config.path
    config_path.unlink()

    response = client_with_session.get(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": f".fmu config at {config_path} does not exist"}


async def test_get_config_with_session_unknown_error(
    mock_token: str, client_with_session: TestClient
) -> None:
    """Test 500 returns if other exceptions are raised."""
    with patch.object(
        ProjectConfigManager,
        "load",
        side_effect=Exception("foo"),
    ):
        response = client_with_session.get(
            ROUTE,
            headers={settings.TOKEN_HEADER_NAME: mock_token},
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "foo"}
