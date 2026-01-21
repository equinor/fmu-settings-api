"""Service for managing mappings in .fmu and business logic."""

from pathlib import Path
from typing import Self

from fmu.datamodels.context.mappings import (
    DataSystem,
    StratigraphyIdentifierMapping,
    StratigraphyMappings,
)
from fmu.settings import ProjectFMUDirectory
from fmu.settings.models.mappings import MappingGroup


class MappingsService:
    """Service for handling mappings."""

    def __init__(self, fmu_dir: ProjectFMUDirectory) -> None:
        """Initialize the service with a project FMU directory."""
        self._fmu_dir = fmu_dir

    @property
    def fmu_dir_path(self) -> Path:
        """Returns the path to the .fmu directory."""
        return self._fmu_dir.path

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

    def group_stratigraphy_mappings(
        self: Self, stratigraphy_mappings: StratigraphyMappings
    ) -> list[MappingGroup]:
        """Group stratigraphy mappings by target and source systems."""
        grouped: dict[
            tuple[str, DataSystem, DataSystem], list[StratigraphyIdentifierMapping]
        ] = {}
        for mapping in stratigraphy_mappings:
            key = (mapping.target_id, mapping.target_system, mapping.source_system)
            grouped.setdefault(key, []).append(mapping)
        return [
            MappingGroup(
                target_id=target_id,
                target_system=target_system,
                source_system=source_system,
                mappings=mappings,
            )
            for (target_id, target_system, source_system), mappings in grouped.items()
        ]
