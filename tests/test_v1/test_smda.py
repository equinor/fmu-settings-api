"""Tests the /api/v1/smda routes."""

from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from fmu.datamodels.fmu_results.fields import (
    CoordinateSystem,
    CountryItem,
    DiscoveryItem,
    StratigraphicColumn,
)

from fmu_settings_api.config import HttpHeader
from fmu_settings_api.models.smda import (
    SmdaFieldSearchResult,
    SmdaFieldUUID,
)

ROUTE = "/api/v1/smda"


@pytest.fixture
async def mock_SmdaAPI_get() -> AsyncGenerator[AsyncMock]:
    """Mocks the get() method on SmdaAPI."""
    with patch("fmu_settings_api.deps.SmdaAPI.get", new_callable=AsyncMock) as get_mock:
        yield get_mock


@pytest.fixture
async def mock_SmdaAPI_post() -> AsyncGenerator[AsyncMock]:
    """Mocks the post() method on SmdaAPI."""
    with patch(
        "fmu_settings_api.deps.SmdaAPI.post", new_callable=AsyncMock
    ) as post_mock:
        yield post_mock


def test_get_health(client_with_session: TestClient, session_tmp_path: Path) -> None:
    """Test 401 returns when the user has no SMDA API key set in their configuration."""
    response = client_with_session.get(f"{ROUTE}/health")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
    assert (
        response.headers[HttpHeader.UPSTREAM_SOURCE_KEY]
        == HttpHeader.UPSTREAM_SOURCE_SMDA
    )
    assert response.json()["detail"] == "User SMDA API key is not configured"


def test_get_health_has_user_api_key(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 401 returns when an API key exists but an SMDA access token is not set."""
    response = client_with_session.patch(
        "/api/v1/user/api_key",
        json={
            "id": "smda_subscription",
            "key": "secret",
        },
    )
    assert response.status_code == status.HTTP_200_OK, response.json()

    response = client_with_session.get(f"{ROUTE}/health")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
    assert (
        response.headers[HttpHeader.UPSTREAM_SOURCE_KEY]
        == HttpHeader.UPSTREAM_SOURCE_SMDA
    )
    assert response.json()["detail"] == "SMDA access token is not set"


async def test_get_health_has_user_api_key_and_access_token(
    client_with_smda_session: TestClient,
    session_tmp_path: Path,
    mock_SmdaAPI_get: AsyncMock,
) -> None:
    """Test 200 returns when an API key and SMDA access token are set."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = httpx.codes.OK
    mock_response.json.return_value = {"status": "ok"}

    mock_SmdaAPI_get.return_value = mock_response

    response = client_with_smda_session.get(f"{ROUTE}/health")
    assert response.status_code == status.HTTP_200_OK, response.json()
    assert (
        response.headers[HttpHeader.UPSTREAM_SOURCE_KEY]
        == HttpHeader.UPSTREAM_SOURCE_SMDA
    )
    assert response.json()["status"] == "ok"


async def test_get_health_request_failure_raises_exception(
    client_with_smda_session: TestClient,
    session_tmp_path: Path,
    mock_SmdaAPI_get: AsyncMock,
) -> None:
    """Tests the request to SMDA failing as a 500 error."""
    mock_request = MagicMock(spec=httpx.Request)
    mock_request.url = "https://smda"
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 401
    mock_SmdaAPI_get.side_effect = httpx.HTTPStatusError(
        "401 Client Error: Access Denied",
        request=mock_request,
        response=mock_response,
    )

    response = client_with_smda_session.get(f"{ROUTE}/health")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
    assert (
        response.headers[HttpHeader.UPSTREAM_SOURCE_KEY]
        == HttpHeader.UPSTREAM_SOURCE_SMDA
    )
    assert response.json()["detail"] == "SMDA error requesting https://smda"


async def test_post_field_succeeds_with_one(
    client_with_smda_session: TestClient,
    session_tmp_path: Path,
    mock_SmdaAPI_post: AsyncMock,
) -> None:
    """Tests that posting a valid search returns a valid result."""
    uuid = uuid4()
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {
            "hits": 1,
            "pages": 1,
            "results": [
                {
                    "identifier": "TROLL",
                    "uuid": str(uuid),
                }
            ],
        }
    }

    mock_SmdaAPI_post.return_value = mock_response

    response = client_with_smda_session.post(
        f"{ROUTE}/field", json={"identifier": "TROLL"}
    )
    assert response.status_code == status.HTTP_200_OK, response.json()
    assert (
        response.headers[HttpHeader.UPSTREAM_SOURCE_KEY]
        == HttpHeader.UPSTREAM_SOURCE_SMDA
    )
    assert SmdaFieldSearchResult.model_validate(
        response.json()
    ) == SmdaFieldSearchResult(
        hits=1,
        pages=1,
        results=[
            SmdaFieldUUID(identifier="TROLL", uuid=uuid),
        ],
    )


async def test_post_field_succeeds_with_none(
    client_with_smda_session: TestClient,
    session_tmp_path: Path,
    mock_SmdaAPI_post: AsyncMock,
) -> None:
    """Tests that posting a valid but non-existent search returns an empty result."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {
            "hits": 0,
            "pages": 0,
            "results": [],
        }
    }

    mock_SmdaAPI_post.return_value = mock_response

    response = client_with_smda_session.post(
        f"{ROUTE}/field", json={"identifier": "DROGON"}
    )

    assert response.status_code == status.HTTP_200_OK, response.json()
    assert (
        response.headers[HttpHeader.UPSTREAM_SOURCE_KEY]
        == HttpHeader.UPSTREAM_SOURCE_SMDA
    )
    assert SmdaFieldSearchResult.model_validate(
        response.json()
    ) == SmdaFieldSearchResult(
        hits=0,
        pages=0,
        results=[],
    )


async def test_post_field_with_no_identifier_raises(
    client_with_smda_session: TestClient,
    session_tmp_path: Path,
    mock_SmdaAPI_post: AsyncMock,
) -> None:
    """Tests that posting an empty field identifier is valid but returns no data."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {
            "hits": 0,
            "pages": 0,
            "results": [],
        }
    }

    mock_SmdaAPI_post.return_value = mock_response
    response = client_with_smda_session.post(f"{ROUTE}/field", json={"identifier": ""})

    assert response.status_code == status.HTTP_200_OK, response.json()
    assert (
        response.headers[HttpHeader.UPSTREAM_SOURCE_KEY]
        == HttpHeader.UPSTREAM_SOURCE_SMDA
    )
    assert SmdaFieldSearchResult.model_validate(
        response.json()
    ) == SmdaFieldSearchResult(
        hits=0,
        pages=0,
        results=[],
    )


async def test_post_field_has_bad_response_raises(
    client_with_smda_session: TestClient,
    session_tmp_path: Path,
    mock_SmdaAPI_post: AsyncMock,
) -> None:
    """Tests that posting a valid response with an invalid response from SMDA fails."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {}

    mock_SmdaAPI_post.return_value = mock_response
    response = client_with_smda_session.post(f"{ROUTE}/field", json={"identifier": ""})

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR, (
        response.json()
    )
    assert (
        response.headers[HttpHeader.UPSTREAM_SOURCE_KEY]
        == HttpHeader.UPSTREAM_SOURCE_SMDA
    )
    assert (
        response.json()["detail"]
        == "Malformed response from SMDA: no 'data' field present"
    )


async def test_post_field_with_no_json_fails(
    client_with_smda_session: TestClient,
    session_tmp_path: Path,
    mock_SmdaAPI_post: AsyncMock,
) -> None:
    """Tests that posting without json causes Pydantic validation errors."""
    response = client_with_smda_session.post(f"{ROUTE}/field")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, (
        response.json()
    )
    assert response.json()["detail"] == [
        {
            "input": None,
            "loc": ["body"],
            "msg": "Field required",
            "type": "missing",
        }
    ]


async def test_post_masterdata_success(
    client_with_smda_session: TestClient,
    session_tmp_path: Path,
) -> None:
    """Tests successful post to masterdata."""
    mock_field_response = MagicMock(spec=httpx.Response)
    mock_field_response.status_code = 200
    mock_field_response.json.return_value = {
        "data": {
            "hits": 1,
            "pages": 1,
            "results": [
                {
                    "country_identifier": "Norway",
                    "identifier": "DROGON",
                    "projected_coordinate_system": "ST_WGS84_UTM37N_P32637",
                    "uuid": uuid4(),
                }
            ],
        }
    }

    with (
        patch("fmu_settings_api.deps.SmdaAPI") as mock_smda_class,
        patch(
            "fmu_settings_api.v1.routes.smda.main.get_coordinate_systems",
            new_callable=AsyncMock,
        ) as mock_get_coordinate_systems,
        patch(
            "fmu_settings_api.v1.routes.smda.main.get_countries",
            new_callable=AsyncMock,
        ) as mock_get_countries,
        patch(
            "fmu_settings_api.v1.routes.smda.main.get_discoveries",
            new_callable=AsyncMock,
        ) as mock_get_discoveries,
        patch(
            "fmu_settings_api.v1.routes.smda.main.get_strat_column_areas",
            new_callable=AsyncMock,
        ) as mock_get_strat_column_areas,
    ):
        mock_smda_instance = AsyncMock()
        mock_smda_instance.field.return_value = mock_field_response
        mock_smda_class.return_value = mock_smda_instance

        mock_get_coordinate_systems.return_value = [
            CoordinateSystem(
                identifier="ST_WGS84_UTM37N_P32637",
                uuid=uuid4(),
            ),
            CoordinateSystem(
                identifier="ST_WGS84_UTM37N_P32638",
                uuid=uuid4(),
            ),
        ]
        mock_get_countries.return_value = [
            CountryItem(identifier="Norway", uuid=uuid4())
        ]
        mock_get_discoveries.return_value = [
            DiscoveryItem(short_identifier="Drogon West", uuid=uuid4()),
            DiscoveryItem(short_identifier="Drogon East", uuid=uuid4()),
        ]
        mock_get_strat_column_areas.return_value = [
            StratigraphicColumn(identifier="LITHO_DROGON", uuid=uuid4()),
            StratigraphicColumn(identifier="LITHO_VISERION", uuid=uuid4()),
        ]
        response = client_with_smda_session.post(
            f"{ROUTE}/masterdata", json=[{"identifier": "DROGON"}]
        )

    assert response.status_code == status.HTTP_200_OK, response.json()
    assert (
        response.headers[HttpHeader.UPSTREAM_SOURCE_KEY]
        == HttpHeader.UPSTREAM_SOURCE_SMDA
    )
    response_data = response.json()
    assert len(response_data["field"]) == 1
    assert response_data["field"][0]["identifier"] == "DROGON"
    assert (
        response_data["field_coordinate_system"]["identifier"]
        == "ST_WGS84_UTM37N_P32637"
    )

    mock_smda_instance.field.assert_called_once_with(
        ["DROGON"],
        columns=[
            "country_identifier",
            "identifier",
            "projected_coordinate_system",
            "uuid",
        ],
    )


async def test_post_masterdata_missing_coordinate_system(
    client_with_smda_session: TestClient,
    session_tmp_path: Path,
) -> None:
    """Tests error when field coordinate system is not found."""
    mock_field_response = MagicMock(spec=httpx.Response)
    mock_field_response.status_code = 200
    mock_field_response.json.return_value = {
        "data": {
            "hits": 0,
            "pages": 0,
            "results": [
                {
                    "country_identifier": "Norway",
                    "identifier": "DROGON",
                    "projected_coordinate_system": "UNKNOWN_CRS",
                    "uuid": uuid4(),
                }
            ],
        }
    }

    with (
        patch("fmu_settings_api.deps.SmdaAPI") as mock_smda_class,
        patch(
            "fmu_settings_api.v1.routes.smda.main.get_coordinate_systems",
            new_callable=AsyncMock,
        ) as mock_get_coordinate_systems,
        patch(
            "fmu_settings_api.v1.routes.smda.main.get_countries",
            new_callable=AsyncMock,
        ) as mock_get_countries,
        patch(
            "fmu_settings_api.v1.routes.smda.main.get_discoveries",
            new_callable=AsyncMock,
        ) as mock_get_discoveries,
        patch(
            "fmu_settings_api.v1.routes.smda.main.get_strat_column_areas",
            new_callable=AsyncMock,
        ) as mock_get_strat_column_areas,
    ):
        mock_smda_instance = AsyncMock()
        mock_smda_instance.field.return_value = mock_field_response
        mock_smda_class.return_value = mock_smda_instance

        # Coordinate systems do not contain field's coordinate system
        mock_get_coordinate_systems.return_value = [
            CoordinateSystem(
                identifier="ST_WGS84_UTM37N_P32637",
                uuid=uuid4(),
            ),
        ]

        mock_get_countries.return_value = []
        mock_get_discoveries.return_value = []
        mock_get_strat_column_areas.return_value = []
        response = client_with_smda_session.post(
            f"{ROUTE}/masterdata", json=[{"identifier": "DROGON"}]
        )

    assert response.status_code == status.HTTP_404_NOT_FOUND, response.json()
    assert (
        response.headers[HttpHeader.UPSTREAM_SOURCE_KEY]
        == HttpHeader.UPSTREAM_SOURCE_SMDA
    )
    expected_msg = (
        "Coordinate system 'UNKNOWN_CRS' referenced by field 'DROGON' "
        "not found in SMDA."
    )
    assert expected_msg in response.json()["detail"]


async def test_post_masterdata_malformed_response(
    client_with_smda_session: TestClient,
    session_tmp_path: Path,
) -> None:
    """Tests error handling for malformed SMDA response."""
    mock_field_response = MagicMock(spec=httpx.Response)
    mock_field_response.status_code = 200
    mock_field_response.json.return_value = {
        "malformed": "response",
    }

    with patch("fmu_settings_api.deps.SmdaAPI") as mock_smda_class:
        mock_smda_instance = AsyncMock()
        mock_smda_instance.field.return_value = mock_field_response
        mock_smda_class.return_value = mock_smda_instance

        response = client_with_smda_session.post(
            f"{ROUTE}/masterdata", json=[{"identifier": "DROGON"}]
        )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR, (
        response.json()
    )
    assert (
        response.headers[HttpHeader.UPSTREAM_SOURCE_KEY]
        == HttpHeader.UPSTREAM_SOURCE_SMDA
    )
    assert "Malformed response from SMDA" in response.json()["detail"]


async def test_post_masterdata_multiple_fields(
    client_with_smda_session: TestClient,
    session_tmp_path: Path,
) -> None:
    """Tests posting multiple fields with duplicate removal."""
    mock_field_response = MagicMock(spec=httpx.Response)
    mock_field_response.status_code = 200
    mock_field_response.json.return_value = {
        "data": {
            "hits": 2,
            "pages": 1,
            "results": [
                {
                    "country_identifier": "Norway",
                    "identifier": "DROGON",
                    "projected_coordinate_system": "ST_WGS84_UTM37N_P32637",
                    "uuid": uuid4(),
                },
                {
                    "country_identifier": "Norway",
                    "identifier": "VISERION",
                    "projected_coordinate_system": "ST_WGS84_UTM37N_P32637",
                    "uuid": uuid4(),
                },
            ],
        }
    }

    with (
        patch("fmu_settings_api.deps.SmdaAPI") as mock_smda_class,
        patch(
            "fmu_settings_api.v1.routes.smda.main.get_coordinate_systems",
            new_callable=AsyncMock,
        ) as mock_get_coordinate_systems,
        patch(
            "fmu_settings_api.v1.routes.smda.main.get_countries",
            new_callable=AsyncMock,
        ) as mock_get_countries,
        patch(
            "fmu_settings_api.v1.routes.smda.main.get_discoveries",
            new_callable=AsyncMock,
        ) as mock_get_discoveries,
        patch(
            "fmu_settings_api.v1.routes.smda.main.get_strat_column_areas",
            new_callable=AsyncMock,
        ) as mock_get_strat_column_areas,
    ):
        mock_smda_instance = AsyncMock()
        mock_smda_instance.field.return_value = mock_field_response
        mock_smda_class.return_value = mock_smda_instance

        mock_get_coordinate_systems.return_value = [
            CoordinateSystem(
                identifier="ST_WGS84_UTM37N_P32637",
                uuid=uuid4(),
            ),
        ]
        mock_get_countries.return_value = [
            CountryItem(identifier="Norway", uuid=uuid4())
        ]
        mock_get_discoveries.return_value = []
        mock_get_strat_column_areas.return_value = []
        response = client_with_smda_session.post(
            f"{ROUTE}/masterdata",
            json=[
                {"identifier": "DROGON"},
                {"identifier": "VISERION"},
                {"identifier": "DROGON"},
            ],
        )

    assert response.status_code == status.HTTP_200_OK, response.json()
    assert (
        response.headers[HttpHeader.UPSTREAM_SOURCE_KEY]
        == HttpHeader.UPSTREAM_SOURCE_SMDA
    )
    response_data = response.json()
    assert len(response_data["field"]) == 2  # noqa: PLR2004

    mock_smda_instance.field.assert_called_once_with(
        ["DROGON", "VISERION"],
        columns=[
            "country_identifier",
            "identifier",
            "projected_coordinate_system",
            "uuid",
        ],
    )


async def test_post_masterdata_empty_field_list(
    client_with_smda_session: TestClient,
    session_tmp_path: Path,
) -> None:
    """Tests when a post with no fields is sent."""
    mock_field_response = MagicMock(spec=httpx.Response)
    mock_field_response.status_code = 200
    mock_field_response.json.return_value = {
        "data": {
            "hits": 0,
            "pages": 0,
            "results": [],
        }
    }

    with (
        patch("fmu_settings_api.deps.SmdaAPI") as mock_smda_class,
        patch(
            "fmu_settings_api.v1.routes.smda.main.get_coordinate_systems",
            new_callable=AsyncMock,
        ) as mock_get_coordinate_systems,
        patch(
            "fmu_settings_api.v1.routes.smda.main.get_countries",
            new_callable=AsyncMock,
        ) as mock_get_countries,
        patch(
            "fmu_settings_api.v1.routes.smda.main.get_discoveries",
            new_callable=AsyncMock,
        ) as mock_get_discoveries,
        patch(
            "fmu_settings_api.v1.routes.smda.main.get_strat_column_areas",
            new_callable=AsyncMock,
        ) as mock_get_strat_column_areas,
    ):
        mock_smda_instance = AsyncMock()
        mock_smda_instance.field.return_value = mock_field_response
        mock_smda_class.return_value = mock_smda_instance

        mock_get_coordinate_systems.return_value = []
        mock_get_countries.return_value = []
        mock_get_discoveries.return_value = []
        mock_get_strat_column_areas.return_value = []
        response = client_with_smda_session.post(
            f"{ROUTE}/masterdata",
            json=[],
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST, response.json()


async def test_post_masterdata_request_fails(
    client_with_smda_session: TestClient,
    session_tmp_path: Path,
    mock_SmdaAPI_post: AsyncMock,
) -> None:
    """Tests when a post when the fields initial request fails."""
    mock_request = MagicMock(spec=httpx.Request)
    mock_request.url = "https://smda"
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 401
    mock_SmdaAPI_post.side_effect = httpx.HTTPStatusError(
        "401 Client Error: Access Denied",
        request=mock_request,
        response=mock_response,
    )

    response = client_with_smda_session.post(
        f"{ROUTE}/masterdata",
        json=[{"identifier": "DROGON"}],
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
    assert (
        response.headers[HttpHeader.UPSTREAM_SOURCE_KEY]
        == HttpHeader.UPSTREAM_SOURCE_SMDA
    )
    assert response.json()["detail"] == "SMDA error requesting https://smda"


async def test_post_masterdata_request_timeout(
    client_with_smda_session: TestClient,
    session_tmp_path: Path,
) -> None:
    """Tests when a post request to SMDA times out."""
    with patch("fmu_settings_api.deps.SmdaAPI") as mock_smda_class:
        mock_smda_instance = AsyncMock()
        mock_smda_instance.field.side_effect = TimeoutError("Request timed out")
        mock_smda_class.return_value = mock_smda_instance

        response = client_with_smda_session.post(
            f"{ROUTE}/masterdata",
            json=[{"identifier": "DROGON"}],
        )

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE, response.json()
    assert (
        response.headers[HttpHeader.UPSTREAM_SOURCE_KEY]
        == HttpHeader.UPSTREAM_SOURCE_SMDA
    )
    assert response.json()["detail"] == "SMDA API request timed out. Please try again."
