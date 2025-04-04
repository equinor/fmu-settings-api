"""Tests the root routes of /api/v1."""

from fastapi import status
from fastapi.testclient import TestClient

from fmu_settings_api.__main__ import app
from fmu_settings_api.config import settings

client = TestClient(app)

ROUTE = "/api/v1/health"


def test_health_check_unauthorized() -> None:
    """Test the health check endpoint with missing token."""
    response = client.get(ROUTE, headers={})
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Not authenticated"}


def test_health_check_invalid_token() -> None:
    """Test the health check endpoint with an invalid token."""
    token = "no" * 32
    response = client.get(ROUTE, headers={settings.TOKEN_HEADER_NAME: token})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "Not authorized"}


def test_health_check_valid_token(mock_token: str) -> None:
    """Test the health check endpoint with a valid token."""
    response = client.get(ROUTE, headers={settings.TOKEN_HEADER_NAME: mock_token})
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}
