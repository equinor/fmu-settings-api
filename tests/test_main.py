"""Tests for the __main__ module."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

from fastapi import status
from fastapi.testclient import TestClient

from fmu_settings_api.__main__ import app
from fmu_settings_api.models import Ok
from fmu_settings_api.session import (
    AccessTokens,
    ProjectSession,
    Session,
    session_manager,
)

client = TestClient(app)


def test_main_invocation() -> None:
    """Tests that the main entry point runs."""


def test_health_check() -> None:
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK, response.json()
    assert response.json() == {"status": "ok"}
    assert Ok() == Ok.model_validate(response.json())


def test_shutdown_releases_project_lock() -> None:
    """Ensure lifespan teardown releases project locks."""
    lock = MagicMock()
    lock.is_acquired.return_value = True
    now = datetime.now(UTC)
    project_session = ProjectSession(
        id="test-session",
        user_fmu_directory=cast("Any", object()),
        created_at=now,
        expires_at=now,
        last_accessed=now,
        access_tokens=AccessTokens(),
        project_fmu_directory=cast("Any", SimpleNamespace(_lock=lock)),
    )

    base_session = Session(
        id="base-session",
        user_fmu_directory=cast("Any", object()),
        created_at=now,
        expires_at=now,
        last_accessed=now,
        access_tokens=AccessTokens(),
    )

    original_storage = session_manager.storage
    session_manager.storage = {
        "non_project": base_session,
        project_session.id: project_session,
    }
    try:
        with TestClient(app):
            lock.release.assert_not_called()
        lock.release.assert_called_once()
    finally:
        session_manager.storage = original_storage
