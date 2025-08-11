"""Tests the SMDA API interface."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

from fmu_settings_api.config import HttpHeader
from fmu_settings_api.interfaces.smda_api import SmdaAPI, SmdaRoutes


@pytest.fixture
def mock_httpx_get() -> Generator[MagicMock]:
    """Mocks methods on SmdaAPI."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    with patch(
        "fmu_settings_api.interfaces.smda_api.httpx.AsyncClient.get",
        return_value=mock_response,
    ) as get:
        yield get


@pytest.fixture
def mock_httpx_post() -> Generator[MagicMock]:
    """Mocks methods on SmdaAPI."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    with patch(
        "fmu_settings_api.interfaces.smda_api.httpx.AsyncClient.post",
        return_value=mock_response,
    ) as post:
        yield post


async def test_smda_get(mock_httpx_get: MagicMock) -> None:
    """Tests the GET method on the SMDA interface."""
    api = SmdaAPI("token", "key")
    res = await api.get(SmdaRoutes.HEALTH)

    mock_httpx_get.assert_called_with(
        f"{SmdaRoutes.BASE_URL}/{SmdaRoutes.HEALTH}",
        headers={
            HttpHeader.CONTENT_TYPE_KEY: HttpHeader.CONTENT_TYPE_JSON,
            HttpHeader.AUTHORIZATION_KEY: "Bearer token",
            HttpHeader.OCP_APIM_SUBSCRIPTION_KEY: "key",
        },
    )
    res.raise_for_status.assert_called_once()  # type: ignore


async def test_smda_post_with_json(mock_httpx_post: MagicMock) -> None:
    """Tests the POST method on the SMDA interface with json."""
    api = SmdaAPI("token", "key")
    res = await api.post(SmdaRoutes.HEALTH, json={"a": "b"})

    mock_httpx_post.assert_called_with(
        f"{SmdaRoutes.BASE_URL}/{SmdaRoutes.HEALTH}",
        headers={
            HttpHeader.CONTENT_TYPE_KEY: HttpHeader.CONTENT_TYPE_JSON,
            HttpHeader.AUTHORIZATION_KEY: "Bearer token",
            HttpHeader.OCP_APIM_SUBSCRIPTION_KEY: "key",
        },
        json={"a": "b"},
    )
    res.raise_for_status.assert_called_once()  # type: ignore


async def test_smda_post_without_json(mock_httpx_post: MagicMock) -> None:
    """Tests the POST method on the SMDA interface without."""
    api = SmdaAPI("token", "key")
    res = await api.post(SmdaRoutes.HEALTH)

    mock_httpx_post.assert_called_with(
        f"{SmdaRoutes.BASE_URL}/{SmdaRoutes.HEALTH}",
        headers={
            HttpHeader.CONTENT_TYPE_KEY: HttpHeader.CONTENT_TYPE_JSON,
            HttpHeader.AUTHORIZATION_KEY: "Bearer token",
            HttpHeader.OCP_APIM_SUBSCRIPTION_KEY: "key",
        },
        json=None,
    )
    res.raise_for_status.assert_called_once()  # type: ignore
