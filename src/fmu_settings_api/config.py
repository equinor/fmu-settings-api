"""Settings used for the API."""

import hashlib
import secrets
from typing import Annotated, Any, Final, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    HttpUrl,
    ValidationError,
    computed_field,
)


def generate_auth_token() -> str:
    """Generates a secure auth token."""
    random_bytes = secrets.token_hex(32)
    return hashlib.sha256(random_bytes.encode()).hexdigest()


def parse_cors(v: Any) -> list[HttpUrl]:
    """Parse CORS.

    Args:
        v: A command separated string or a list of origins

    Returns:
        A list of CORS origins

    Raises:
        ValueError: If the input is not parseable into a list of origins
    """
    if isinstance(v, str) and not v.startswith("["):
        return [HttpUrl(i.strip()) for i in v.split(",")]
    if isinstance(v, list):
        return [HttpUrl(str(item).strip()) for item in v]
    raise ValueError(f"Invalid list of origins: {v}")


class HttpHeader:
    """Contains Http header keys and values for API requests."""

    API_TOKEN_KEY: Final[str] = "x-fmu-settings-api"
    UPSTREAM_SOURCE_KEY: Final[str] = "x-upstream-source"
    UPSTREAM_SOURCE_SMDA: Final[str] = "SMDA"
    WWW_AUTHENTICATE_KEY: Final[str] = "WWW-Authenticate"
    WWW_AUTHENTICATE_COOKIE: Final[str] = "Cookie-Auth"
    CONTENT_TYPE_KEY: Final[str] = "Content-Type"
    CONTENT_TYPE_JSON: Final[str] = "application/json"
    AUTHORIZATION_KEY: Final[str] = "authorization"
    OCP_APIM_SUBSCRIPTION_KEY: Final[str] = "Ocp-Apim-Subscription-Key"


class APISettings(BaseModel):
    """Settings used for the API."""

    API_V1_PREFIX: str = Field(default="/api/v1", frozen=True)
    TOKEN: str = Field(
        default_factory=generate_auth_token,
        pattern=r"^[a-fA-F0-9]{64}$",
    )

    SESSION_COOKIE_KEY: str = Field(default="fmu_settings_session", frozen=True)
    # 20 minute session length
    SESSION_EXPIRE_SECONDS: int = Field(default=1200, frozen=True)

    FRONTEND_HOST: HttpUrl = Field(default=HttpUrl("http://localhost:8000"))
    BACKEND_CORS_ORIGINS: Annotated[list[HttpUrl], BeforeValidator(parse_cors)] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        """Returns a validated list of valid origins."""
        all_origins = set()
        all_origins.add(str(self.FRONTEND_HOST).rstrip("/"))

        for origin in self.BACKEND_CORS_ORIGINS:
            all_origins.add(str(origin).rstrip("/"))

        return list(all_origins)

    def update_frontend_host(
        self: Self, host: str, port: int, protocol: str = "http"
    ) -> None:
        """Updates the frontend host, which will be included in CORS origins.

        Args:
            host: The frontend host
            port: The frontend port
            protocol: The http or https protocol. Default: http
        """
        try:
            self.FRONTEND_HOST = HttpUrl(f"{protocol}://{host}:{port}")
        except ValidationError as e:
            raise e


settings = APISettings()


async def get_settings() -> APISettings:
    """Returns the API settings.

    This can be used for dependency injection in FastAPI routes.
    """
    return settings
