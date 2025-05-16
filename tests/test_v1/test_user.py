"""Tests the /api/v1/user routes."""

from fastapi import status
from fastapi.testclient import TestClient
from fmu.settings._fmu_dir import UserFMUDirectory
from fmu.settings.models.user_config import UserConfig

from fmu_settings_api.__main__ import app
from fmu_settings_api.config import settings

client = TestClient(app)

ROUTE = "/api/v1/user"


def test_get_user_fmu_unauthenticated() -> None:
    """Tests that user routes required a token."""
    response = client.get(ROUTE, headers={})
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Not authenticated"}


def test_get_user_fmu_no_session(mock_token: str) -> None:
    """Tests that user routes required a session."""
    response = client.get(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "No active session found"}


def test_get_user_fmu_config(client_with_session: TestClient, mock_token: str) -> None:
    """Tests that getting a user config functions correctly."""
    response = client_with_session.get(
        ROUTE,
        headers={settings.TOKEN_HEADER_NAME: mock_token},
    )
    assert response.status_code == status.HTTP_200_OK
    user_fmu_dir = UserFMUDirectory()
    assert user_fmu_dir.config.load() == UserConfig.model_validate(response.json())


def test_patch_invalid_api_token_key_to_user_fmu_config(
    client_with_session: TestClient, mock_token: str
) -> None:
    """Tests that submitting an unsupported API does return 422."""
    response = client_with_session.patch(
        f"{ROUTE}/api_key",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={
            "id": "foo",
            "key": "secret",
        },
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json()["detail"] == "API id foo is not known or supported"


def test_patch_api_token_to_user_fmu_config(
    client_with_session: TestClient, mock_token: str
) -> None:
    """Tests that submitting a valid API key pair saved to the user configuration."""
    user_fmu_dir = UserFMUDirectory()
    assert user_fmu_dir.get_config_value("user_api_keys.smda_subscription") is None

    response = client_with_session.patch(
        f"{ROUTE}/api_key",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={
            "id": "smda_subscription",
            "key": "secret",
        },
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["message"] == "Saved API key for smda_subscription"

    user_fmu_dir = UserFMUDirectory()
    assert (
        user_fmu_dir.get_config_value(
            "user_api_keys.smda_subscription"
        ).get_secret_value()
        == "secret"
    )


def test_api_token_is_not_leaked_with_user_fmu_config(
    client_with_session: TestClient, mock_token: str
) -> None:
    """Tests that retrieving the user configuration does not leak API tokens."""
    response = client_with_session.patch(
        f"{ROUTE}/api_key",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
        json={
            "id": "smda_subscription",
            "key": "secret",
        },
    )
    assert response.status_code == status.HTTP_200_OK

    response = client_with_session.get(
        f"{ROUTE}",
        headers={settings.TOKEN_HEADER_NAME: mock_token},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["user_api_keys"]["smda_subscription"] == "**********"
