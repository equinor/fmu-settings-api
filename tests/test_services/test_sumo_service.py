"""Tests for SumoService."""

from unittest.mock import patch

import pytest

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


@pytest.mark.parametrize("force_refresh", [False, True])
def test_login(force_refresh: bool) -> None:
    """Tests that login passes the refresh option to the Sumo interface."""
    with patch("fmu_settings_api.interfaces.sumo_api.SumoApi.login") as login_mock:
        SumoService().login(force_refresh=force_refresh)

    login_mock.assert_called_once_with(force_refresh=force_refresh)
