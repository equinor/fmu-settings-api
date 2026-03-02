"""Tests for the __main__ module."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from fmu_settings_api.__main__ import (
    app,
    logging_http_exception_handler,
    logging_request_validation_exception_handler,
)
from fmu_settings_api.middleware.logging import LoggingMiddleware
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


def test_http_exception_logs_request_failed_details() -> None:
    """Ensure HTTPException emits a detailed request_failed log entry."""
    test_app = FastAPI()
    test_app.add_middleware(LoggingMiddleware)
    test_app.add_exception_handler(
        StarletteHTTPException,
        logging_http_exception_handler,
    )
    test_app.add_exception_handler(
        RequestValidationError,
        logging_request_validation_exception_handler,
    )

    @test_app.get("/test")
    async def failing_route() -> None:
        raise HTTPException(status_code=401, detail="Not authorized")

    with patch("fmu_settings_api.__main__.logger") as mock_logger:
        with TestClient(test_app) as local_client:
            response = local_client.get("/test")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        warning_calls = [
            call
            for call in mock_logger.warning.call_args_list
            if call[0][0] == "request_failed"
        ]
        assert len(warning_calls) > 0
        log_data = warning_calls[0][1]
        assert log_data["status_code"] == status.HTTP_401_UNAUTHORIZED
        assert log_data["error"] == "Not authorized"
        assert log_data["error_type"] == "HTTPException"
        assert "duration_ms" in log_data
        assert log_data["duration_ms"] >= 0


def test_validation_exception_logs_request_failed_details() -> None:
    """Ensure validation errors emit a detailed request_failed log entry."""
    test_app = FastAPI()
    test_app.add_middleware(LoggingMiddleware)
    test_app.add_exception_handler(
        StarletteHTTPException,
        logging_http_exception_handler,
    )
    test_app.add_exception_handler(
        RequestValidationError,
        logging_request_validation_exception_handler,
    )

    @test_app.get("/test")
    async def validation_route(limit: int) -> dict[str, int]:
        return {"limit": limit}

    with patch("fmu_settings_api.__main__.logger") as mock_logger:
        with TestClient(test_app) as local_client:
            response = local_client.get("/test?limit=bad")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        warning_calls = [
            call
            for call in mock_logger.warning.call_args_list
            if call[0][0] == "request_failed"
        ]
        assert len(warning_calls) > 0
        log_data = warning_calls[0][1]
        assert log_data["status_code"] == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert isinstance(log_data["error"], list)
        assert len(log_data["error"]) > 0
        assert log_data["error_type"] == "RequestValidationError"
        assert "duration_ms" in log_data
        assert log_data["duration_ms"] >= 0
