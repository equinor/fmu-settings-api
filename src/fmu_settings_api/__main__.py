"""The main entry point for fmu-settings-api."""

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import uvicorn
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fmu.settings._fmu_dir import UserFMUDirectory
from fmu.settings._init import init_user_fmu_directory
from fmu.settings._resources.user_session_log_manager import UserSessionLogManager
from fmu.settings.models.event_info import EventInfo
from starlette.middleware.cors import CORSMiddleware

from .config import HttpHeader, settings
from .logging import get_logger, setup_logging
from .middleware.logging import LoggingMiddleware
from .models import Ok
from .session import ProjectSession, session_manager
from .v1.main import api_v1_router


def custom_generate_unique_id(route: APIRoute) -> str:
    """Generates a unique id per route."""
    return f"{route.tags[0]}-{route.name}"


logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """App lifespan for startup/shutdown housekeeping.

    On shutdown, releases any acquired project locks so other processes
    are not blocked by stale locks after a graceful stop.
    """
    logger.info(
        "starting_application",
        app_name=settings.APP_NAME,
        app_version=settings.APP_VERSION,
        log_level=settings.log_level,
        log_format=settings.log_format,
        environment=settings.environment,
    )

    yield

    logger.info("stopping_application")

    for session in tuple(session_manager.storage.values()):
        if not isinstance(session, ProjectSession):
            continue

        lock = session.project_fmu_directory._lock
        if lock.is_acquired():
            with suppress(Exception):
                lock.release()


app = FastAPI(
    title="FMU Settings API",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)
app.add_middleware(LoggingMiddleware)
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

    try:
        user_fmu_dir = UserFMUDirectory()
        fmu_dir_status = "loaded"
    except FileNotFoundError:
        user_fmu_dir = init_user_fmu_directory()
        fmu_dir_status = "initialized"

    log_manager = UserSessionLogManager(user_fmu_dir)

    settings.log_level = log_level.upper()  # type: ignore[assignment]
    setup_logging(settings, fmu_log_manager=log_manager, log_entry_class=EventInfo)

    if fmu_dir_status == "initialized":
        logger.info("fmu_directory_initialized", path=str(user_fmu_dir.path))
    else:
        logger.debug("fmu_directory_loaded", path=str(user_fmu_dir.path))

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
