"""Service for managing mappings in .fmu and business logic."""

from pathlib import Path
from typing import Self

from fmu.datamodels.context.mappings import (
    DataSystem,
    MappingType,
)
from fmu.settings import (
    InternalMappings,
    InternalRelationType,
    InternalStratigraphyMappings,
    InternalWellboreIdentifierMapping,
    InternalWellboreMappings,
    ProjectFMUDirectory,
)

from fmu_settings_api.interfaces import WellboreMappingsFileIO


class MappingsService:
    """Service for handling mappings."""

    def __init__(self, fmu_dir: ProjectFMUDirectory) -> None:
        """Initialize the service with a project FMU directory."""
        self._fmu_dir = fmu_dir
        self._wellbore_mappings_file_io = WellboreMappingsFileIO(fmu_dir)

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

    def import_rms_eclipse_csv(
        self: Self, relative_path: str | Path | None = None
    ) -> InternalWellboreMappings:
        """Import RMS-to-simulator wellbore mappings from an rms_eclipse CSV file."""
        self._fmu_dir._lock.ensure_can_write()
        wellbore_mappings = self._wellbore_mappings_file_io.read_rms_eclipse_csv(
            relative_path
        )
        return self._fmu_dir.mappings.update_internal_wellbore_mappings(
            wellbore_mappings
        )

    def export_rms_simulator_csv(
        self: Self, relative_path: str | Path | None = None
    ) -> None:
        """Export RMS-to-simulator wellbore mappings as rms_simulator CSV."""
        self._fmu_dir._lock.ensure_can_write()
        filtered_wellbore_mappings = self._filter_wellbore_mappings(
            wellbore_mappings=self._fmu_dir.mappings.internal_wellbore_mappings,
            source_system=DataSystem.rms,
            target_system=DataSystem.simulator,
            relation_type=InternalRelationType.primary,
        )
        if not filtered_wellbore_mappings:
            raise ValueError(
                "No rms-to-simulator primary wellbore mappings available to export "
                "as rms_simulator.csv"
            )
        self._wellbore_mappings_file_io.write_rms_simulator_csv(
            filtered_wellbore_mappings, relative_path
        )

    def export_rms_simulator_renaming_table(
        self: Self, relative_path: str | Path | None = None
    ) -> None:
        """Export RMS-to-simulator wellbore mappings as rms_simulator renaming table."""
        self._fmu_dir._lock.ensure_can_write()
        filtered_wellbore_mappings = self._filter_wellbore_mappings(
            wellbore_mappings=self._fmu_dir.mappings.internal_wellbore_mappings,
            source_system=DataSystem.rms,
            target_system=DataSystem.simulator,
            relation_type=InternalRelationType.primary,
        )
        if not filtered_wellbore_mappings:
            raise ValueError(
                "No rms-to-simulator primary wellbore mappings available to export "
                "as rms_simulator.renaming_table"
            )
        self._wellbore_mappings_file_io.write_rms_simulator_renaming_table(
            filtered_wellbore_mappings, relative_path
        )

    def export_rms_pdm_renaming_table(
        self: Self, relative_path: str | Path | None = None
    ) -> None:
        """Export RMS-to-PDM wellbore mappings as rms_pdm renaming table."""
        self._fmu_dir._lock.ensure_can_write()
        filtered_wellbore_mappings = self._filter_wellbore_mappings(
            wellbore_mappings=self._fmu_dir.mappings.internal_wellbore_mappings,
            source_system=DataSystem.rms,
            target_system=DataSystem.pdm,
            relation_type=InternalRelationType.primary,
        )
        if not filtered_wellbore_mappings:
            raise ValueError(
                "No rms-to-pdm primary wellbore mappings available to export as "
                "rms_pdm.renaming_table"
            )
        self._wellbore_mappings_file_io.write_rms_pdm_renaming_table(
            filtered_wellbore_mappings, relative_path
        )

    def _filter_wellbore_mappings(
        self: Self,
        *,
        wellbore_mappings: InternalWellboreMappings,
        source_system: DataSystem,
        target_system: DataSystem,
        relation_type: InternalRelationType,
    ) -> list[InternalWellboreIdentifierMapping]:
        """Return wellbore mappings matching source, target, and relation."""
        return [
            mapping
            for mapping in wellbore_mappings
            if (
                mapping.source_system == source_system
                and mapping.target_system == target_system
                and mapping.mapping_type == MappingType.wellbore
                and mapping.relation_type == relation_type
                and mapping.target_id is not None
            )
        ]

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
