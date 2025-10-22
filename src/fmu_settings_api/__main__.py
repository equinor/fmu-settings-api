"""The main entry point for fmu-settings-api."""

import asyncio
import signal
import sys
from types import FrameType

import uvicorn
from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from .config import HttpHeader, settings
from .models import Ok
from .v1.main import api_v1_router


def custom_generate_unique_id(route: APIRoute) -> str:
    """Generates a unique id per route."""
    return f"{route.tags[0]}-{route.name}"


app = FastAPI(
    title="FMU Settings API",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)
app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)


@app.get(
    "/health",
    tags=["health"],
    response_model=Ok,
    summary="A health check on the application",
    description=(
        "This route requires no form of authentication or authorization. "
        "It can be used to check if the application is running and responsive."
    ),
)
async def health_check() -> Ok:
    """Simple health check endpoint."""
    return Ok()


def run_server(  # noqa: PLR0913
    *,
    host: str = "127.0.0.1",
    port: int = 8001,
    frontend_host: str | None = None,
    frontend_port: int | None = None,
    token: str | None = None,
    reload: bool = False,
    log_level: str = "critical",
) -> None:
    """Starts the API server."""
    log_level = log_level.lower()

    if token:
        settings.TOKEN = token

    if frontend_host is not None and frontend_port is not None:
        settings.update_frontend_host(host=frontend_host, port=frontend_port)

    if settings.all_cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.all_cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=[HttpHeader.UPSTREAM_SOURCE_KEY],
        )

    def signal_handler(signum: int, frame: FrameType | None) -> None:
        """Gracefully handles interrupt shutdowns."""
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if reload:
        uvicorn.run(
            app=app,
            host=host,
            port=port,
            reload=True,
            reload_dirs=["src"],
            reload_includes=[".env"],
            log_level=log_level,
        )
    else:
        server_config = uvicorn.Config(
            app=app, host=host, port=port, log_level=log_level
        )
        server = uvicorn.Server(server_config)

        try:
            asyncio.run(server.serve())
        except KeyboardInterrupt:
            sys.exit(0)


if __name__ == "__main__":
    run_server()
