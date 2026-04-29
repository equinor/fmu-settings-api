"""Service for managing mappings in .fmu and business logic."""

from pathlib import Path
from typing import Self

from fmu.datamodels.context.mappings import (
    DataSystem,
    MappingType,
)
from fmu.settings import (
    InternalMappings,
    InternalStratigraphyMappings,
    ProjectFMUDirectory,
)


class MappingsService:
    """Service for handling mappings."""

    def __init__(self, fmu_dir: ProjectFMUDirectory) -> None:
        """Initialize the service with a project FMU directory."""
        self._fmu_dir = fmu_dir

    @property
    def fmu_dir_path(self) -> Path:
        """Returns the path to the .fmu directory."""
        return self._fmu_dir.path

    def list_internal_stratigraphy_mappings(self: Self) -> InternalStratigraphyMappings:
        """Get all the internal stratigraphy mappings in the FMU directory."""
        return self._fmu_dir.mappings.internal_stratigraphy_mappings

    def update_internal_stratigraphy_mappings(
        self: Self, stratigraphy_mappings: InternalStratigraphyMappings
    ) -> InternalStratigraphyMappings:
        """Save internal stratigraphy mappings to the mappings resource.

        All existing internal stratigraphy mappings will be overwritten.
        """
        return self._fmu_dir.mappings.update_internal_stratigraphy_mappings(
            stratigraphy_mappings
        )

    def get_internal_mappings_by_source_system(
        self,
        mapping_type: MappingType,
        source_system: DataSystem,
    ) -> InternalMappings:
        """Get internal mappings filtered by mapping type and source system.

        Raises:
            ValueError: If mapping type is unsupported
        """
        if mapping_type == MappingType.stratigraphy:
            try:
                stratigraphy_mappings = self.list_internal_stratigraphy_mappings()
            except FileNotFoundError:
                stratigraphy_mappings = InternalStratigraphyMappings(root=[])

            filtered_mappings = InternalStratigraphyMappings(
                root=[
                    mapping
                    for mapping in stratigraphy_mappings
                    if mapping.source_system == source_system
                ]
            )
            return InternalMappings(stratigraphy=filtered_mappings)

        raise ValueError(f"Mapping type '{mapping_type}' is not yet supported")

    def update_internal_mappings_by_source_system(
        self,
        mapping_type: MappingType,
        source_system: DataSystem,
        mappings: InternalStratigraphyMappings,
    ) -> None:
        """Replace internal mappings for a specific mapping type and source system.

        Raises:
            ValueError: If mapping type is unsupported
        """
        if mapping_type == MappingType.stratigraphy:
            if any(mapping.source_system != source_system for mapping in mappings):
                raise ValueError(
                    "All mappings in the request body must use the requested "
                    f"source system '{source_system.value}'"
                )

            try:
                other_mappings = [
                    mapping
                    for mapping in self.list_internal_stratigraphy_mappings()
                    if mapping.source_system != source_system
                ]
            except FileNotFoundError:
                other_mappings = []

            self.update_internal_stratigraphy_mappings(
                InternalStratigraphyMappings(root=[*mappings, *other_mappings])
            )
            return

        raise ValueError(f"Mapping type '{mapping_type}' is not yet supported")
