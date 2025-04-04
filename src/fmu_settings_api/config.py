"""Settings used for the API."""

import hashlib
import secrets
from typing import Annotated, Any, Self

from pydantic import AnyUrl, BaseModel, BeforeValidator, Field, computed_field


def generate_auth_token() -> str:
    """Generates a secure auth token."""
    random_bytes = secrets.token_hex(32)
    return hashlib.sha256(random_bytes.encode()).hexdigest()


def parse_cors(v: Any) -> list[str] | str:
    """Parse CORS."""
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",")]
    if isinstance(v, list | str):
        return v
    raise ValueError(v)


class APISettings(BaseModel):
    """Settings used for the API."""

    API_V1_PREFIX: str = Field(default="/api/v1", frozen=True)
    TOKEN_HEADER_NAME: str = Field(default="x-fmu-settings-api", frozen=True)
    SESSION_COOKIE_KEY: str = Field(default="fmu_settings_session", frozen=True)
    SESSION_EXPIRE_SECONDS: int = Field(default=3600, frozen=True)
    DOMAIN: str = "localhost"
    TOKEN: str = Field(
        default_factory=generate_auth_token, pattern=r"^[a-fA-F0-9]{64}$"
    )

    FRONTEND_HOST: str = "http://localhost:8000"
    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        """Returns a list of valid origins."""
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            self.FRONTEND_HOST
        ]

    def update_frontend_host(self: Self, host: str, port: int) -> None:
        """Updates the authentication token."""
        self.FRONTEND_HOST = f"{host}:{port}"


settings = APISettings()


async def get_settings() -> APISettings:
    """Returns the API settings.

    This can be used for dependency injection in FastAPI routes.
    """
    return settings
