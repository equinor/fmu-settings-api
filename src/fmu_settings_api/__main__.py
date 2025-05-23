"""The main entry point for fmu-settings-api."""

import asyncio

import uvicorn
from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from .config import settings
from .models import HealthCheck
from .v1.main import api_v1_router


def custom_generate_unique_id(route: APIRoute) -> str:
    """Generates a unique id per route."""
    return f"{route.tags[0]}-{route.name}"


app = FastAPI(
    title="FMU Settings API",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)
app.include_router(api_v1_router)


@app.get(
    "/health",
    tags=["app"],
    response_model=HealthCheck,
    summary="A health check on the application",
    description=(
        "This route requires no form of authentication or authorization. "
        "It can be used to check if the application is running and responsive."
    ),
)
async def health_check() -> HealthCheck:
    """Simple health check endpoint."""
    return HealthCheck()


def run_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8001,
    frontend_host: str | None = None,
    frontend_port: int | None = None,
    token: str | None = None,
) -> None:
    """Starts the API server."""
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
        )

    server_config = uvicorn.Config(app=app, host=host, port=port)
    server = uvicorn.Server(server_config)

    asyncio.run(server.serve())


if __name__ == "__main__":
    run_server()
