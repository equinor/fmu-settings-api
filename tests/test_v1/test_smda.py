"""Tests the /api/v1/smda routes."""

from pathlib import Path

from fastapi import status
from fastapi.testclient import TestClient

ROUTE = "/api/v1/smda"


def test_get_check(client_with_session: TestClient, session_tmp_path: Path) -> None:
    """Test 401 returns when the user has no SMDA API key set in their configuration."""
    response = client_with_session.get(f"{ROUTE}/check")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
    assert response.json()["detail"] == "User SMDA API key is not configured"


def test_get_check_has_user_api_key(
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

    response = client_with_session.get(f"{ROUTE}/check")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
    assert response.json()["detail"] == "SMDA access token is not set"


def test_get_check_has_user_api_key_and_access_token(
    client_with_smda_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 401 returns when an API key exists but an SMDA access token is not set."""
    response = client_with_smda_session.get(f"{ROUTE}/check")
    assert response.status_code == status.HTTP_200_OK, response.json()
    assert response.json()["status"] == "ok"
