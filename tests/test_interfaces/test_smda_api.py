"""Tests the SMDA API interface."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import httpx
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
    """Tests the POST method on the SMDA interface without json."""
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


async def test_strat_units_with_identifier(mock_httpx_post: MagicMock) -> None:
    """Tests strat_units method sends correct payload with identifier."""
    api = SmdaAPI("token", "key")
    res = await api.strat_units("LITHO_DROGON")

    mock_httpx_post.assert_called_with(
        f"{SmdaRoutes.BASE_URL}/{SmdaRoutes.STRAT_UNITS_SEARCH}",
        headers={
            HttpHeader.CONTENT_TYPE_KEY: HttpHeader.CONTENT_TYPE_JSON,
            HttpHeader.AUTHORIZATION_KEY: "Bearer token",
            HttpHeader.OCP_APIM_SUBSCRIPTION_KEY: "key",
        },
        json={
            "_projection": "identifier,uuid",
            "strat_column_identifier": "LITHO_DROGON",
        },
    )
    res.raise_for_status.assert_called_once()  # type: ignore


async def test_strat_units_with_columns(mock_httpx_post: MagicMock) -> None:
    """Tests strat_units method with custom column projection."""
    api = SmdaAPI("token", "key")
    res = await api.strat_units(
        "LITHO_DROGON",
        columns=["identifier", "uuid", "strat_unit_type"],
    )

    mock_httpx_post.assert_called_with(
        f"{SmdaRoutes.BASE_URL}/{SmdaRoutes.STRAT_UNITS_SEARCH}",
        headers={
            HttpHeader.CONTENT_TYPE_KEY: HttpHeader.CONTENT_TYPE_JSON,
            HttpHeader.AUTHORIZATION_KEY: "Bearer token",
            HttpHeader.OCP_APIM_SUBSCRIPTION_KEY: "key",
        },
        json={
            "_projection": "identifier,uuid,strat_unit_type",
            "strat_column_identifier": "LITHO_DROGON",
        },
    )
    res.raise_for_status.assert_called_once()  # type: ignore


async def test_smda_api_coordinate_system(mock_httpx_post: MagicMock) -> None:
    """Tests coordinate_system sends correct payload with identifier and columns."""
    api = SmdaAPI("token", "key")

    crs_identifier = ["EPSG:4326", "EPSG:25832"]
    columns = ["identifier", "uuid", "name"]

    res = await api.coordinate_system(
        crs_identifier=crs_identifier,
        columns=columns,
    )

    mock_httpx_post.assert_called_with(
        f"{SmdaRoutes.BASE_URL}/{SmdaRoutes.COORDINATE_SYSTEM_SEARCH}",
        headers={
            HttpHeader.CONTENT_TYPE_KEY: HttpHeader.CONTENT_TYPE_JSON,
            HttpHeader.AUTHORIZATION_KEY: "Bearer token",
            HttpHeader.OCP_APIM_SUBSCRIPTION_KEY: "key",
        },
        json={
            "_projection": "identifier,uuid,name",
            "_items": 9999,
            "identifier": crs_identifier,
        },
    )
    res.raise_for_status.assert_called_once()  # type: ignore


async def test_smda_api_coordinate_system_without_identifier_columns(
    mock_httpx_post: MagicMock,
) -> None:
    """Tests coordinate_system sends default payload without identifier and columns."""
    api = SmdaAPI("token", "key")

    res = await api.coordinate_system()

    mock_httpx_post.assert_called_with(
        f"{SmdaRoutes.BASE_URL}/{SmdaRoutes.COORDINATE_SYSTEM_SEARCH}",
        headers={
            HttpHeader.CONTENT_TYPE_KEY: HttpHeader.CONTENT_TYPE_JSON,
            HttpHeader.AUTHORIZATION_KEY: "Bearer token",
            HttpHeader.OCP_APIM_SUBSCRIPTION_KEY: "key",
        },
        json={
            "_projection": "identifier,uuid",
            "_items": 9999,
        },
    )
    res.raise_for_status.assert_called_once()  # type: ignore


async def test_smda_strat_column_areas(mock_httpx_post: MagicMock) -> None:
    """Tests strat_column_areas sends correct payload."""
    api = SmdaAPI("token", "key")

    res = await api.strat_column_areas(["FIELD_A"])

    mock_httpx_post.assert_called_with(
        f"{SmdaRoutes.BASE_URL}/{SmdaRoutes.STRAT_COLUMN_AREAS_SEARCH}",
        headers=api._headers,
        json={
            "_projection": "identifier,uuid",
            "strat_area_identifier": ["FIELD_A"],
            "strat_column_status": "official",
        },
    )
    res.raise_for_status.assert_called_once()  # type: ignore


async def test_smda_health_ok(mock_httpx_get: MagicMock) -> None:
    """Tests health returns True when status is OK."""
    api = SmdaAPI("token", "key")
    mock_httpx_get.return_value.status_code = httpx.codes.OK

    res = await api.health()

    assert res is True


async def test_smda_field_search(mock_httpx_post: MagicMock) -> None:
    """Tests field search sends correct payload."""
    api = SmdaAPI("token", "key")

    res = await api.field(["FIELD_A"])

    mock_httpx_post.assert_called_with(
        f"{SmdaRoutes.BASE_URL}/{SmdaRoutes.FIELDS_SEARCH}",
        headers=api._headers,
        json={
            "_projection": "identifier,uuid",
            "identifier": ["FIELD_A"],
        },
    )
    res.raise_for_status.assert_called_once()  # type: ignore


async def test_smda_country_search(mock_httpx_post: MagicMock) -> None:
    """Tests country search sends correct payload."""
    api = SmdaAPI("token", "key")

    res = await api.country(["NO"])

    mock_httpx_post.assert_called_with(
        f"{SmdaRoutes.BASE_URL}/{SmdaRoutes.COUNTRIES_SEARCH}",
        headers=api._headers,
        json={
            "_projection": "identifier,uuid",
            "identifier": ["NO"],
        },
    )
    res.raise_for_status.assert_called_once()  # type: ignore


async def test_smda_discovery_search(mock_httpx_post: MagicMock) -> None:
    """Tests discovery search sends correct payload."""
    api = SmdaAPI("token", "key")

    res = await api.discovery(["FIELD_A"])

    mock_httpx_post.assert_called_with(
        f"{SmdaRoutes.BASE_URL}/{SmdaRoutes.DISCOVERIES_SEARCH}",
        headers=api._headers,
        json={
            "_projection": "identifier,uuid",
            "field_identifier": ["FIELD_A"],
        },
    )
    res.raise_for_status.assert_called_once()  # type: ignore
