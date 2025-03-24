"""Root configuration for pytest."""

import pytest


@pytest.fixture
def mock_token() -> str:
    """Sets a token."""
    from fmu_settings_api.config import settings

    token = "safe" * 16
    settings.TOKEN = token
    return token
