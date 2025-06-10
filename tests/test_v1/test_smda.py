"""Tests the /api/v1/smda routes."""

from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from fmu_settings_api.models.smda import (
    SMDAFieldSearchResult,
    SMDAFieldUUID,
)

ROUTE = "/api/v1/smda"


@pytest.fixture
async def mock_SmdaAPI_get() -> AsyncGenerator[AsyncMock]:
    """Mocks the get() method on SmdaAPI."""
    with patch(
        "fmu_settings_api.v1.routes.smda.SmdaAPI.get", new_callable=AsyncMock
    ) as get_mock:
        yield get_mock


@pytest.fixture
async def mock_SmdaAPI_post() -> AsyncGenerator[AsyncMock]:
    """Mocks the post() method on SmdaAPI."""
    with patch(
        "fmu_settings_api.v1.routes.smda.SmdaAPI.post", new_callable=AsyncMock
    ) as post_mock:
        yield post_mock


def test_get_health(client_with_session: TestClient, session_tmp_path: Path) -> None:
    """Test 401 returns when the user has no SMDA API key set in their configuration."""
    response = client_with_session.get(f"{ROUTE}/health")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
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
    assert response.json()["detail"] == "SMDA access token is not set"


async def test_get_health_has_user_api_key_and_access_token(
    client_with_smda_session: TestClient,
    session_tmp_path: Path,
    mock_SmdaAPI_get: AsyncMock,
) -> None:
    """Test 401 returns when an API key exists but an SMDA access token is not set."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = httpx.codes.OK
    mock_response.json.return_value = {"status": "ok"}

    mock_SmdaAPI_get.return_value = mock_response

    response = client_with_smda_session.get(f"{ROUTE}/health")
    assert response.status_code == status.HTTP_200_OK, response.json()
    assert response.json()["status"] == "ok"


async def test_get_health_request_failure_raises_exception(
    client_with_smda_session: TestClient,
    session_tmp_path: Path,
    mock_SmdaAPI_get: AsyncMock,
) -> None:
    """Tests the request to SMDA failing as a 500 error."""
    mock_SmdaAPI_get.side_effect = httpx.HTTPError("401 Client Error: Access Denied")

    response = client_with_smda_session.get(f"{ROUTE}/health")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR, (
        response.json()
    )
    assert response.json()["detail"] == "401 Client Error: Access Denied"


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
    assert SMDAFieldSearchResult.model_validate(
        response.json()
    ) == SMDAFieldSearchResult(
        hits=1,
        pages=1,
        results=[
            SMDAFieldUUID(identifier="TROLL", uuid=uuid),
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
    assert SMDAFieldSearchResult.model_validate(
        response.json()
    ) == SMDAFieldSearchResult(
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
    assert SMDAFieldSearchResult.model_validate(
        response.json()
    ) == SMDAFieldSearchResult(
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
        response.json()["detail"]
        == "500: Malformed response from SMDA: no 'data' field present"
    )


async def test_post_field_with_no_json_fails(
    client_with_smda_session: TestClient,
    session_tmp_path: Path,
    mock_SmdaAPI_post: AsyncMock,
) -> None:
    """Tests that posting without json causes Pydantic validation errors."""
    response = client_with_smda_session.post(f"{ROUTE}/field")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, response.json()
    assert response.json()["detail"] == [
        {
            "input": None,
            "loc": ["body"],
            "msg": "Field required",
            "type": "missing",
        }
    ]
