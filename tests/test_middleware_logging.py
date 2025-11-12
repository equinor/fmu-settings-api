"""Tests for the logging middleware."""

import contextlib
from unittest.mock import patch

from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from fmu_settings_api.middleware.logging import LoggingMiddleware


def test_logging_middleware_logs_request_started() -> None:
    """Test middleware logs request_started event."""
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/test")
    async def test_route() -> dict[str, str]:
        return {"status": "ok"}

    with patch("fmu_settings_api.middleware.logging.logger") as mock_logger:
        with TestClient(app) as client:
            client.get("/test")

        calls = mock_logger.info.call_args_list
        request_started_call = [
            call for call in calls if call[0][0] == "request_started"
        ]
        assert len(request_started_call) > 0


def test_logging_middleware_logs_request_completed() -> None:
    """Test middleware logs request_completed event with duration."""
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/test")
    async def test_route() -> dict[str, str]:
        return {"status": "ok"}

    with patch("fmu_settings_api.middleware.logging.logger") as mock_logger:
        with TestClient(app) as client:
            response = client.get("/test")

        assert response.status_code == status.HTTP_200_OK

        calls = mock_logger.info.call_args_list
        request_completed_call = [
            call for call in calls if call[0][0] == "request_completed"
        ]
        assert len(request_completed_call) > 0

        completed_call = request_completed_call[0]
        assert "duration_ms" in completed_call[1]


def test_logging_middleware_logs_request_failed() -> None:
    """Test middleware logs request_failed event on exception."""
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/test")
    async def test_route() -> None:
        raise ValueError("Test error")

    with (
        patch("fmu_settings_api.middleware.logging.logger") as mock_logger,
        TestClient(app) as client,
        contextlib.suppress(ValueError),
    ):
        client.get("/test")

        calls = mock_logger.exception.call_args_list
        assert len(calls) > 0
        assert calls[0][0][0] == "request_failed"


def test_logging_middleware_captures_query_params() -> None:
    """Test middleware captures query params when present."""
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/test")
    async def test_route() -> dict[str, str]:
        return {"status": "ok"}

    with patch("fmu_settings_api.middleware.logging.logger") as mock_logger:
        with TestClient(app) as client:
            client.get("/test?param1=value1&param2=value2")

        calls = mock_logger.info.call_args_list
        request_started_call = [
            call for call in calls if call[0][0] == "request_started"
        ]
        assert len(request_started_call) > 0
        assert "query_params" in request_started_call[0][1]


def test_logging_middleware_no_query_params() -> None:
    """Test middleware handles requests without query params."""
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/test")
    async def test_route() -> dict[str, str]:
        return {"status": "ok"}

    with patch("fmu_settings_api.middleware.logging.logger") as mock_logger:
        with TestClient(app) as client:
            client.get("/test")

        calls = mock_logger.info.call_args_list
        request_started_call = [
            call for call in calls if call[0][0] == "request_started"
        ]
        assert len(request_started_call) > 0
        assert request_started_call[0][1]["query_params"] is None


def test_logging_middleware_captures_method_and_path() -> None:
    """Test middleware captures HTTP method and path."""
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.post("/api/test")
    async def test_route() -> dict[str, str]:
        return {"status": "ok"}

    with patch("fmu_settings_api.middleware.logging.logger") as mock_logger:
        with TestClient(app) as client:
            client.post("/api/test")

        calls = mock_logger.info.call_args_list
        request_started_call = [
            call for call in calls if call[0][0] == "request_started"
        ]
        assert len(request_started_call) > 0
        assert request_started_call[0][1]["method"] == "POST"
        assert request_started_call[0][1]["path"] == "/api/test"


def test_logging_middleware_captures_status_code() -> None:
    """Test middleware captures response status code."""
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/test")
    async def test_route() -> JSONResponse:
        return JSONResponse({"status": "created"}, status_code=201)

    with patch("fmu_settings_api.middleware.logging.logger") as mock_logger:
        with TestClient(app) as client:
            response = client.get("/test")

        assert response.status_code == status.HTTP_201_CREATED

        calls = mock_logger.info.call_args_list
        request_completed_call = [
            call for call in calls if call[0][0] == "request_completed"
        ]
        assert len(request_completed_call) > 0
        assert request_completed_call[0][1]["status_code"] == status.HTTP_201_CREATED


def test_logging_middleware_logs_error_details() -> None:
    """Test middleware logs error type and message on failure."""
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/test")
    async def test_route() -> None:
        raise RuntimeError("Something went wrong")

    with (
        patch("fmu_settings_api.middleware.logging.logger") as mock_logger,
        TestClient(app) as client,
        contextlib.suppress(RuntimeError),
    ):
        client.get("/test")

        calls = mock_logger.exception.call_args_list
        assert len(calls) > 0
        assert calls[0][1]["error_type"] == "RuntimeError"
        assert "Something went wrong" in calls[0][1]["error"]


def test_logging_middleware_duration_is_positive() -> None:
    """Test middleware logs positive duration."""
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/test")
    async def test_route() -> dict[str, str]:
        return {"status": "ok"}

    with patch("fmu_settings_api.middleware.logging.logger") as mock_logger:
        with TestClient(app) as client:
            client.get("/test")

        calls = mock_logger.info.call_args_list
        request_completed_call = [
            call for call in calls if call[0][0] == "request_completed"
        ]
        assert len(request_completed_call) > 0
        duration = request_completed_call[0][1]["duration_ms"]
        assert duration >= 0
