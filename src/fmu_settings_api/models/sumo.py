"""Models for Sumo requests and responses."""

from fmu_settings_api.models.common import BaseResponseModel


class SumoAsset(BaseResponseModel):
    """A Sumo asset available to the user."""

    name: str
    """Name of the asset in Sumo."""


class SumoLoginRequest(BaseResponseModel):
    """Options for logging in to Sumo."""

    force_refresh: bool = False
    """Invalidate cached Microsoft access tokens before login."""
