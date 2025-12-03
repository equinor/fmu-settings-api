"""Logging middleware for request/response tracking."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from fmu_settings_api.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response

logger = get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all requests and responses with duration tracking."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Log request and response details."""
        start_time = time.time()

        logger.info(
            "request_started",
            method=request.method,
            path=request.url.path,
            query_params=str(request.query_params) if request.query_params else None,
            client_ip=request.client.host if request.client else None,
        )

        try:
            response = await call_next(request)
            duration = time.time() - start_time

            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration * 1000, 2),
            )
            return response
        except HTTPException as e:
            duration = time.time() - start_time
            logger.warning(
                "request_failed",
                method=request.method,
                path=request.url.path,
                status_code=e.status_code,
                error=e.detail,
                error_type=type(e).__name__,
                duration_ms=round(duration * 1000, 2),
            )
            raise
        except Exception as e:
            duration = time.time() - start_time
            logger.exception(
                "request_failed",
                method=request.method,
                path=request.url.path,
                error=str(e),
                error_type=type(e).__name__,
                duration_ms=round(duration * 1000, 2),
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "An unexpected error occurred."},
            )
