"""Tests for the __main__ module."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from fmu.settings import MigrationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from fmu_settings_api.__main__ import (
    add_frontend,
    app,
    logging_http_exception_handler,
    logging_migration_exception_handler,
    logging_request_validation_exception_handler,
    run_server,
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


def test_add_frontend_serves_spa_without_hiding_api_routes(tmp_path: Path) -> None:
    """Serve frontend files and keep explicit API routes at higher priority."""
    frontend_directory = tmp_path / "static"
    assets_directory = frontend_directory / "assets"
    assets_directory.mkdir(parents=True)
    (frontend_directory / "index.html").write_text(
        "<html>frontend</html>", encoding="utf-8"
    )
    (assets_directory / "app.js").write_text("app", encoding="utf-8")

    test_app = FastAPI()

    @test_app.get("/api/value")
    async def get_value() -> dict[str, str]:
        return {"value": "api"}

    add_frontend(test_app, frontend_directory)
    local_client = TestClient(test_app)

    api_response = local_client.get("/api/value")
    route_response = local_client.get(
        "/project/masterdata", headers={"accept": "text/html"}
    )
    asset_response = local_client.get("/assets/app.js")

    assert api_response.json() == {"value": "api"}
    assert route_response.text == "<html>frontend</html>"
    assert asset_response.text == "app"


def test_run_server_adds_frontend(tmp_path: Path) -> None:
    """Add the frontend when its directory is supplied."""
    with (
        patch("fmu_settings_api.__main__.UserFMUDirectory") as user_directory,
        patch("fmu_settings_api.__main__.UserSessionLogManager"),
        patch("fmu_settings_api.__main__.setup_logging"),
        patch("fmu_settings_api.__main__.uvicorn.run") as uvicorn_run,
        patch("fmu_settings_api.__main__.app") as test_app,
        patch("fmu_settings_api.__main__.add_frontend") as add_frontend_mock,
    ):
        user_directory.return_value.path = tmp_path
        run_server(frontend_directory=tmp_path, reload=True)

    add_frontend_mock.assert_called_once_with(test_app, tmp_path)
    assert uvicorn_run.call_args.kwargs["port"] == 8000


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


def test_migration_error_from_dependency_returns_422_and_logs_original_error() -> None:
    """Handle a migration error raised directly by a dependency.

    For example, an SMDA dependency can fail while loading UserConfig before the
    route runs. The central migration handler must log the original error and return
    HTTP 422.
    """
    test_app = FastAPI()
    test_app.add_middleware(LoggingMiddleware)
    test_app.add_exception_handler(
        MigrationError,
        logging_migration_exception_handler,
    )
    migration_error = MigrationError("Stored UserConfig cannot be migrated")

    async def failing_dependency() -> None:
        raise migration_error

    @test_app.get("/test", dependencies=[Depends(failing_dependency)])
    async def dependency_route() -> None:
        pass

    with (
        patch("fmu_settings_api.__main__.logger") as mock_logger,
        TestClient(test_app) as local_client,
    ):
        response = local_client.get("/test")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {"detail": str(migration_error)}
    mock_logger.exception.assert_called_once()
    log_data = mock_logger.exception.call_args.kwargs
    assert log_data["status_code"] == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert log_data["error"] == str(migration_error)
    assert log_data["error_type"] == "MigrationError"


def test_http_exception_caused_by_migration_error_uses_migration_handler() -> None:
    """Handle a migration error wrapped in an HTTPException.

    For example, opening a project can catch a ProjectConfig MigrationError as a
    ValueError and wrap it in an HTTPException. The central HTTP handler must pass the
    original cause to the migration handler, which logs it and returns HTTP 422.
    """
    test_app = FastAPI()
    test_app.add_middleware(LoggingMiddleware)
    test_app.add_exception_handler(
        MigrationError,
        logging_migration_exception_handler,
    )
    test_app.add_exception_handler(
        StarletteHTTPException,
        logging_http_exception_handler,
    )
    migration_error = MigrationError("Stored ProjectConfig cannot be migrated")

    @test_app.get("/test")
    async def wrapped_migration_route() -> None:
        try:
            raise migration_error
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Invalid project") from error

    with (
        patch("fmu_settings_api.__main__.logger") as mock_logger,
        TestClient(test_app) as local_client,
    ):
        response = local_client.get("/test")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {"detail": str(migration_error)}
    mock_logger.exception.assert_called_once()
    mock_logger.warning.assert_not_called()
    log_data = mock_logger.exception.call_args.kwargs
    assert log_data["status_code"] == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert log_data["error"] == str(migration_error)
    assert log_data["error_type"] == "MigrationError"


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
