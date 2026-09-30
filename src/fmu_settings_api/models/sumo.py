"""Models for Sumo responses."""

from fmu_settings_api.models.common import BaseResponseModel


class SumoAsset(BaseResponseModel):
    """A Sumo asset available to the user."""

    name: str
    """Name of the asset in Sumo."""
