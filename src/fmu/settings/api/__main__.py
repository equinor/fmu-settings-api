"""The main entry point for fmu-settings-api."""

import uvicorn
from fastapi import FastAPI

app = FastAPI(title="FMU Settings API")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Simple health check endpoint."""
    return {"status": "ok"}


def run_server(host: str = "127.0.0.1", port: int = 8001) -> None:
    """Starts the API server."""
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
