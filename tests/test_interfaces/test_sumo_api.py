"""Tests the Sumo API interface."""

import json
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import httpx
import pytest

from fmu_settings_api.interfaces.sumo_api import (
    SumoApi,
    SumoAuthenticationRequiredError,
    SumoInvalidResponseError,
    SumoUnavailableError,
)


@pytest.fixture
def mock_sumo_client() -> Generator[tuple[MagicMock, MagicMock]]:
    """Mocks the context-managed Sumo client."""
    with patch("fmu_settings_api.interfaces.sumo_api.SumoClient") as client_class:
        client = client_class.return_value.__enter__.return_value
        client.authenticate.return_value = "token"
        yield client_class, client


def test_get_assets_returns_sorted_assets_with_write_access(
    mock_sumo_client: tuple[MagicMock, MagicMock],
) -> None:
    """Tests that only sorted assets with user write access are returned."""
    client_class, client = mock_sumo_client
    client.get.return_value.json.return_value = {
        "Read only": ["read"],
        "Drogon": ["read", "write"],
        "Alpha": ["write"],
        "No access": [],
    }

    assets = SumoApi().get_assets()

    assert [asset.name for asset in assets] == ["Alpha", "Drogon"]
    client_class.assert_called_once_with(env="prod", interactive=False)
    client.authenticate.assert_called_once_with()
    client.get.assert_called_once_with("/userpermissions")


def test_get_assets_uses_selected_environment(
    mock_sumo_client: tuple[MagicMock, MagicMock],
) -> None:
    """Tests that asset requests use the selected Sumo environment."""
    client_class, client = mock_sumo_client
    client.get.return_value.json.return_value = {}

    SumoApi(environment="dev").get_assets()

    client_class.assert_called_once_with(env="dev", interactive=False)


def test_get_assets_requires_cached_login(
    mock_sumo_client: tuple[MagicMock, MagicMock],
) -> None:
    """Tests that missing cached login is reported without interactive login."""
    client_class, client = mock_sumo_client
    client.authenticate.side_effect = Exception(
        "No valid authorization provider found."
    )

    with pytest.raises(SumoAuthenticationRequiredError, match="login is required"):
        SumoApi().get_assets()

    client_class.assert_called_once_with(env="prod", interactive=False)
    client.get.assert_not_called()


def test_get_assets_reports_unavailable_for_unexpected_authentication_error(
    mock_sumo_client: tuple[MagicMock, MagicMock],
) -> None:
    """Tests that unexpected authentication errors are translated."""
    _, client = mock_sumo_client
    authentication_error = RuntimeError("Unexpected authentication error")
    client.authenticate.side_effect = authentication_error

    with pytest.raises(
        SumoUnavailableError, match="Unable to authenticate"
    ) as exc_info:
        SumoApi().get_assets()

    assert exc_info.value.__cause__ is authentication_error
    client.get.assert_not_called()


@pytest.mark.parametrize(
    "response",
    [
        {"Drogon": "write"},
        {"Drogon": [1]},
        ["Drogon"],
    ],
)
def test_get_assets_rejects_invalid_response(
    mock_sumo_client: tuple[MagicMock, MagicMock], response: object
) -> None:
    """Tests that an asset response with an unexpected structure is rejected."""
    _, client = mock_sumo_client
    client.get.return_value.json.return_value = response

    with pytest.raises(SumoInvalidResponseError, match="invalid asset response"):
        SumoApi().get_assets()


def test_get_assets_rejects_invalid_json(
    mock_sumo_client: tuple[MagicMock, MagicMock],
) -> None:
    """Tests that a Sumo response without JSON is rejected."""
    _, client = mock_sumo_client
    client.get.return_value.json.side_effect = json.JSONDecodeError("invalid", "", 0)

    with pytest.raises(SumoInvalidResponseError, match="invalid asset response"):
        SumoApi().get_assets()


def test_get_assets_reports_unavailable_sumo(
    mock_sumo_client: tuple[MagicMock, MagicMock],
) -> None:
    """Tests that Sumo connection errors are translated."""
    _, client = mock_sumo_client
    client.get.side_effect = httpx.ConnectError(
        "Connection failed", request=httpx.Request("GET", "https://sumo.example")
    )

    with pytest.raises(SumoUnavailableError, match="Unable to get assets"):
        SumoApi().get_assets()


def test_get_assets_reports_unavailable_when_client_construction_fails() -> None:
    """Tests that Sumo client construction failures are translated."""
    discovery_error = Exception("unexpected discovery failure")
    with (
        patch(
            "fmu_settings_api.interfaces.sumo_api.SumoClient",
            side_effect=discovery_error,
        ),
        pytest.raises(SumoUnavailableError, match="Unable to get assets"),
    ):
        SumoApi().get_assets()


def test_get_assets_requires_login_after_unauthorized_response(
    mock_sumo_client: tuple[MagicMock, MagicMock],
) -> None:
    """Tests that a rejected cached token requires a new login."""
    _, client = mock_sumo_client
    request = httpx.Request("GET", "https://sumo.example/userpermissions")
    response = httpx.Response(401, request=request)
    client.get.side_effect = httpx.HTTPStatusError(
        "Unauthorized", request=request, response=response
    )

    with pytest.raises(SumoAuthenticationRequiredError, match="login is required"):
        SumoApi().get_assets()


def test_login_uses_interactive_production_client(
    mock_sumo_client: tuple[MagicMock, MagicMock],
) -> None:
    """Tests that explicit production login uses interactive authentication."""
    client_class, client = mock_sumo_client

    SumoApi().login()

    client_class.assert_called_once_with(env="prod", interactive=True)
    client.authenticate.assert_called_once_with()


def test_login_reports_incomplete_login(
    mock_sumo_client: tuple[MagicMock, MagicMock],
) -> None:
    """Tests that an incomplete interactive login is reported."""
    _, client = mock_sumo_client
    client.authenticate.return_value = None

    with pytest.raises(SumoAuthenticationRequiredError, match="not completed"):
        SumoApi().login()


def test_login_reports_unavailable_sumo(
    mock_sumo_client: tuple[MagicMock, MagicMock],
) -> None:
    """Tests that connection errors preventing interactive login are translated."""
    client_class, _ = mock_sumo_client
    client_class.side_effect = httpx.ConnectError(
        "Connection failed", request=httpx.Request("GET", "https://sumo.example")
    )

    with pytest.raises(SumoUnavailableError, match="Unable to connect"):
        SumoApi().login()


def test_login_reports_unavailable_for_invalid_discovery() -> None:
    """Tests that Sumo client construction failures prevent login cleanly."""
    with (
        patch(
            "fmu_settings_api.interfaces.sumo_api.SumoClient",
            side_effect=Exception("unexpected discovery failure"),
        ),
        pytest.raises(SumoUnavailableError, match="Unable to connect"),
    ):
        SumoApi().login()


def test_login_reports_unavailable_for_unexpected_authentication_error(
    mock_sumo_client: tuple[MagicMock, MagicMock],
) -> None:
    """Tests that unexpected authentication errors are translated."""
    _, client = mock_sumo_client
    authentication_error = RuntimeError("Unexpected authentication error")
    client.authenticate.side_effect = authentication_error

    with pytest.raises(
        SumoUnavailableError, match="Unable to authenticate"
    ) as exc_info:
        SumoApi().login()

    assert exc_info.value.__cause__ is authentication_error
