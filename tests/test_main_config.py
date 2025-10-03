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
