"""Tests the /api/v1/sumo routes."""

from unittest.mock import patch

from fastapi import status
from fastapi.testclient import TestClient

from fmu_settings_api.__main__ import app
from fmu_settings_api.interfaces import (
    SumoAuthenticationRequiredError,
    SumoInvalidResponseError,
    SumoUnavailableError,
)
from fmu_settings_api.models.sumo import SumoAsset

client = TestClient(app)
ROUTE = "/api/v1/sumo"


def test_sumo_requires_session() -> None:
    """Both Sumo routes require an active user session."""
    assert client.get(f"{ROUTE}/assets").status_code == status.HTTP_401_UNAUTHORIZED
    assert client.post(f"{ROUTE}/login").status_code == status.HTTP_401_UNAUTHORIZED


# GET sumo/assets #


async def test_get_sumo_assets_success(
    client_with_session: TestClient,
) -> None:
    """Tests that Sumo assets with write access are returned from the service."""
    assets = [SumoAsset(name="Alpha"), SumoAsset(name="Drogon")]
    with patch(
        "fmu_settings_api.services.sumo.SumoService.get_assets",
        return_value=assets,
    ):
        response = client_with_session.get(f"{ROUTE}/assets")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [{"name": "Alpha"}, {"name": "Drogon"}]


async def test_get_sumo_assets_requires_login(
    client_with_session: TestClient,
) -> None:
    """Tests that 424 is returned when the user must log in to Sumo."""
    with patch(
        "fmu_settings_api.services.sumo.SumoService.get_assets",
        side_effect=SumoAuthenticationRequiredError("Sumo login is required"),
    ):
        response = client_with_session.get(f"{ROUTE}/assets")

    assert response.status_code == status.HTTP_424_FAILED_DEPENDENCY
    assert response.json() == {"detail": "Sumo login is required"}


async def test_get_sumo_assets_invalid_response(
    client_with_session: TestClient,
) -> None:
    """Tests that 502 is returned for an invalid Sumo asset response."""
    with patch(
        "fmu_settings_api.services.sumo.SumoService.get_assets",
        side_effect=SumoInvalidResponseError("Sumo returned an invalid asset response"),
    ):
        response = client_with_session.get(f"{ROUTE}/assets")

    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    assert response.json() == {"detail": "Sumo returned an invalid asset response"}


async def test_get_sumo_assets_unavailable(
    client_with_session: TestClient,
) -> None:
    """Tests that 503 is returned when the Sumo API is unavailable."""
    with patch(
        "fmu_settings_api.services.sumo.SumoService.get_assets",
        side_effect=SumoUnavailableError("Unable to get assets from Sumo"),
    ):
        response = client_with_session.get(f"{ROUTE}/assets")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {"detail": "Unable to get assets from Sumo"}


# POST sumo/login #


async def test_login_to_sumo_success(
    client_with_session: TestClient,
) -> None:
    """Tests that an interactive Sumo login returns success."""
    with patch("fmu_settings_api.services.sumo.SumoService.login") as login_mock:
        response = client_with_session.post(f"{ROUTE}/login")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}
    login_mock.assert_called_once_with()


async def test_login_to_sumo_not_completed(
    client_with_session: TestClient,
) -> None:
    """Tests that 424 is returned when the Sumo login is not completed."""
    with patch(
        "fmu_settings_api.services.sumo.SumoService.login",
        side_effect=SumoAuthenticationRequiredError("Sumo login was not completed"),
    ):
        response = client_with_session.post(f"{ROUTE}/login")

    assert response.status_code == status.HTTP_424_FAILED_DEPENDENCY
    assert response.json() == {"detail": "Sumo login was not completed"}


async def test_login_to_sumo_unavailable(
    client_with_session: TestClient,
) -> None:
    """Tests that 503 is returned when Sumo cannot start the login flow."""
    with patch(
        "fmu_settings_api.services.sumo.SumoService.login",
        side_effect=SumoUnavailableError("Unable to connect to Sumo"),
    ):
        response = client_with_session.post(f"{ROUTE}/login")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {"detail": "Unable to connect to Sumo"}
