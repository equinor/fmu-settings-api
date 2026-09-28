"""Service for Sumo operations."""

from fmu_settings_api.interfaces import SumoApi
from fmu_settings_api.models.sumo import SumoAsset


class SumoService:
    """Get user assets and start a Sumo login."""

    def get_assets(self) -> list[SumoAsset]:
        """Get the Sumo assets to which the user has write access."""
        return SumoApi().get_assets()

    def login(self) -> None:
        """Start an interactive Sumo login."""
        SumoApi().login()
