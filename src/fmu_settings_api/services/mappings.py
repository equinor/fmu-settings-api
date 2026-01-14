"""Service for managing mappings in .fmu and business logic."""

from typing import Self

from fmu.datamodels.context.mappings import StratigraphyMappings
from fmu.settings import ProjectFMUDirectory


class MappingsService:
    """Service for handling mappings."""

    def __init__(self, fmu_dir: ProjectFMUDirectory) -> None:
        """Initialize the service with a project FMU directory."""
        self._fmu_dir = fmu_dir

    def list_stratigraphy_mappings(self: Self) -> StratigraphyMappings:
        """Get all the stratigraphy mappings in the FMU directory."""
        return self._fmu_dir.mappings.stratigraphy_mappings

    def update_stratigraphy_mappings(
        self: Self, stratigraphy_mappings: StratigraphyMappings
    ) -> StratigraphyMappings:
        """Save stratigraphy mappings to the mappings resource.

        All existing stratigraphy mappings will be overwritten.
        """
        return self._fmu_dir.mappings.update_stratigraphy_mappings(
            stratigraphy_mappings
        )
