"""Tests config.py and APISettings."""

from typing import Any

import pytest
from pydantic import HttpUrl, ValidationError

from fmu_settings_api.config import (
    APISettings,
    generate_auth_token,
    get_settings,
    parse_cors,
    settings,
)


def test_generator_auth_token() -> None:
    """Tests that the token is of the correct size."""
    token = generate_auth_token()
    assert isinstance(token, str)
    assert len(token) == 64  # noqa: PLR2004
    assert token != generate_auth_token()


@pytest.mark.parametrize(
    "given, expected",
    [
        ("http://localhost", [HttpUrl("http://localhost")]),
        (
            ["http://example.com ", "https://localhost"],
            [HttpUrl("http://example.com"), HttpUrl("https://localhost")],
        ),
        (
            " http://localhost:8000, https://www.example.com",
            [HttpUrl("http://localhost:8000"), HttpUrl("https://www.example.com")],
        ),
    ],
)
def test_parse_cors(given: Any, expected: Any) -> None:
    """Tests parsing a list or csv list of valid origins."""
    assert parse_cors(given) == expected


def test_parse_cors_raises() -> None:
    """Tests parse_cors raises on invalid origins list."""
    with pytest.raises(ValueError, match="Invalid list of origins"):
        parse_cors('["http://localhost","www.example.com"]')


def test_all_cors_origins() -> None:
    """Tests that the computed field returns correctly."""
    assert settings.all_cors_origins == [str(settings.FRONTEND_HOST).strip("/")]


def test_all_cors_origins_with_extra_backend() -> None:
    """Tests that additional backend origins are validated and concatenated."""
    extra_origin = HttpUrl("https://example.com")
    settings = APISettings(BACKEND_CORS_ORIGINS=[extra_origin])
    assert set(settings.all_cors_origins) == {
        str(extra_origin).rstrip("/"),
        str(settings.FRONTEND_HOST).rstrip("/"),
    }


def test_update_frontend_host() -> None:
    """Tests that updating the frontend host works."""
    assert HttpUrl("http://localhost:8000") == settings.FRONTEND_HOST
    settings.update_frontend_host("localhost", 5555)
    expected = HttpUrl("http://localhost:5555")
    assert expected == settings.FRONTEND_HOST
    assert settings.all_cors_origins == [str(expected).strip("/")]

    # With https
    settings.update_frontend_host("localhost", 5556, protocol="https")
    expected = HttpUrl("https://localhost:5556")
    assert expected == settings.FRONTEND_HOST
    assert settings.all_cors_origins == [str(expected).strip("/")]


def test_update_frontend_host_invalid_protocol() -> None:
    """Tests that update_frontend_host rejects non-http protocols."""
    with pytest.raises(ValidationError, match="URL scheme should be 'http' or 'https'"):
        settings.update_frontend_host("localhost", 5555, protocol="ftp")


async def test_get_settings() -> None:
    """Tests that get_settings returns settings."""
    assert settings == await get_settings()


def test_log_level_default() -> None:
    """Test log_level defaults to INFO."""
    settings = APISettings()
    assert settings.log_level == "INFO"


def test_log_format_default() -> None:
    """Test log_format defaults to console."""
    settings = APISettings()
    assert settings.log_format == "console"


def test_environment_default() -> None:
    """Test environment defaults to development."""
    settings = APISettings()
    assert settings.environment == "development"


def test_is_production_property_true() -> None:
    """Test is_production returns True for production environment."""
    settings = APISettings(environment="production")
    assert settings.is_production is True


def test_is_production_property_false() -> None:
    """Test is_production returns False for non-production environments."""
    settings = APISettings(environment="development")
    assert settings.is_production is False


def test_app_name_constant() -> None:
    """Test APP_NAME is set correctly."""
    settings = APISettings()
    assert settings.APP_NAME == "fmu-settings-api"


def test_app_version_constant() -> None:
    """Test APP_VERSION is set from package version."""
    settings = APISettings()
    assert settings.APP_VERSION is not None
    assert isinstance(settings.APP_VERSION, str)


def test_session_expire_seconds() -> None:
    """Test SESSION_EXPIRE_SECONDS is set correctly."""
    settings = APISettings()
    expected_seconds = 1200  # 20 minutes
    assert expected_seconds == settings.SESSION_EXPIRE_SECONDS


def test_log_level_accepts_valid_values() -> None:
    """Test log_level accepts valid logging levels."""
    for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        settings = APISettings(log_level=level)  # type: ignore[arg-type]
        assert settings.log_level == level


def test_log_format_accepts_valid_values() -> None:
    """Test log_format accepts valid format types."""
    for fmt in ["console", "json"]:
        settings = APISettings(log_format=fmt)  # type: ignore[arg-type]
        assert settings.log_format == fmt


def test_environment_accepts_valid_values() -> None:
    """Test environment accepts valid environment types."""
    for env in ["development", "production"]:
        settings = APISettings(environment=env)  # type: ignore[arg-type]
        assert settings.environment == env
