"""Tests for the __main__ module."""

from fastapi import status
from fastapi.testclient import TestClient

from fmu_settings_api.__main__ import app
from fmu_settings_api.models import Ok

client = TestClient(app)


def test_main_invocation() -> None:
    """Tests that the main entry point runs."""


def test_health_check() -> None:
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK, response.json()
    assert response.json() == {"status": "ok"}
    assert Ok() == Ok.model_validate(response.json())
