"""Tests the SMDA API interface."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

from fmu_settings_api.interfaces.smda_api import SmdaAPI, SmdaRoutes


@pytest.fixture
def mock_requests_get() -> Generator[MagicMock]:
    """Mocks methods on SmdaAPI."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    with patch(
        "fmu_settings_api.interfaces.smda_api.requests.get", return_value=mock_response
    ) as get:
        yield get


async def test_smda_get(mock_requests_get: MagicMock) -> None:
    """Tests the GET method on the SMDA interface."""
    api = SmdaAPI("token", "key")
    res = await api.get(SmdaRoutes.HEALTH)

    mock_requests_get.assert_called_with(
        f"{SmdaRoutes.BASE_URL}/{SmdaRoutes.HEALTH}",
        headers={
            "Content-Type": "application/json",
            "authorization": "Bearer token",
            "Ocp-Apim-Subscription-Key": "key",
        },
    )
    res.raise_for_status.assert_called_once()  # type: ignore
