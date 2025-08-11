"""Tests the root routes of /api/v1."""

from fastapi import status
from fastapi.testclient import TestClient

from fmu_settings_api.__main__ import app
from fmu_settings_api.config import HttpHeader
from fmu_settings_api.models import Ok

client = TestClient(app)

ROUTE = "/api/v1/health"


def test_health_check_no_session() -> None:
    """Test the health check endpoint with missing token and no session."""
    response = client.get(ROUTE)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
    assert response.json() == {"detail": "No active session found"}


def test_health_check_no_session_bad_token() -> None:
    """Test the health check endpoint with an invalid token but no session."""
    token = "no" * 32
    response = client.get(ROUTE, headers={HttpHeader.API_TOKEN_KEY: token})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
    assert response.json() == {"detail": "No active session found"}


def test_health_check_no_session_valid_token(mock_token: str) -> None:
    """Test the health check endpoint with a valid token but no session."""
    response = client.get(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
    assert response.json() == {"detail": "No active session found"}


def test_health_check_no_session_valid_session(client_with_session: TestClient) -> None:
    """Test the health check endpoint with a valid session."""
    response = client_with_session.get(ROUTE)
    assert response.status_code == status.HTTP_200_OK, response.json()
    assert response.json() == {"status": "ok"}
    assert Ok() == Ok.model_validate(response.json())


def test_health_check_no_session_valid_session_invalid_token(
    client_with_session: TestClient,
) -> None:
    """Test the health check endpoint with a valid session and invalid token."""
    token = "no" * 32
    response = client_with_session.get(ROUTE, headers={HttpHeader.API_TOKEN_KEY: token})
    assert response.status_code == status.HTTP_200_OK, response.json()
    assert response.json() == {"status": "ok"}
    assert Ok() == Ok.model_validate(response.json())


def test_health_check_no_session_valid_session_valid_token(
    client_with_session: TestClient, mock_token: str
) -> None:
    """Test the health check endpoint with a valid session and valid token."""
    response = client_with_session.get(
        ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token}
    )
    assert response.status_code == status.HTTP_200_OK, response.json()
    assert response.json() == {"status": "ok"}
    assert Ok() == Ok.model_validate(response.json())
