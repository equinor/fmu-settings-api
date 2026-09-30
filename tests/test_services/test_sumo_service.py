"""Tests for SumoService."""

from unittest.mock import patch

from fmu_settings_api.models.sumo import SumoAsset
from fmu_settings_api.services.sumo import SumoService


def test_get_assets() -> None:
    """Return the assets from the Sumo interface."""
    assets = [SumoAsset(name="TestAsset")]
    with patch(
        "fmu_settings_api.interfaces.sumo_api.SumoApi.get_assets", return_value=assets
    ) as get_assets_mock:
        result = SumoService().get_assets()

    assert result == assets
    get_assets_mock.assert_called_once_with()


def test_login() -> None:
    """Delegate the interactive login to the Sumo interface."""
    with patch("fmu_settings_api.interfaces.sumo_api.SumoApi.login") as login_mock:
        SumoService().login()

    login_mock.assert_called_once_with()
