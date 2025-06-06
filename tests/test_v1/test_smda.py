"""Tests the /api/v1/smda routes."""

from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import requests
from fastapi import status
from fastapi.testclient import TestClient

from fmu_settings_api.interfaces.smda_api import SmdaRoutes

ROUTE = "/api/v1/smda"


@pytest.fixture
async def mock_SmdaAPI_get() -> AsyncGenerator[AsyncMock]:
    """Mocks methods on SmdaAPI."""
    with patch(
        "fmu_settings_api.v1.routes.smda.SmdaAPI.get", new_callabe=AsyncMock()
    ) as get:
        yield get


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

    def request_route_ok(route: str) -> None:
        assert route == SmdaRoutes.HEALTH

    mock_SmdaAPI_get.callable = request_route_ok
    response = client_with_smda_session.get(f"{ROUTE}/health")
    assert response.status_code == status.HTTP_200_OK, response.json()
    assert response.json()["status"] == "ok"


async def test_get_health_request_failure_raises_exception(
    client_with_smda_session: TestClient,
    session_tmp_path: Path,
    mock_SmdaAPI_get: AsyncMock,
) -> None:
    """Tests the request to SMDA failing as a 500 error."""

    def request_not_ok(route: str) -> None:
        raise requests.exceptions.HTTPError("401 Client Error: Access Denied")

    mock_SmdaAPI_get.side_effect = request_not_ok
    response = client_with_smda_session.get(f"{ROUTE}/health")
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR, (
        response.json()
    )
    assert response.json()["detail"] == "401 Client Error: Access Denied"
