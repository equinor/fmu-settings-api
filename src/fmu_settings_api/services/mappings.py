"""Service for managing mappings in .fmu and business logic."""

from collections.abc import Callable
from pathlib import Path
from typing import Final, Self, TypeAlias, cast

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

AnyInternalMappings: TypeAlias = InternalStratigraphyMappings | InternalWellboreMappings


class MappingsService:
    """Service for handling mappings."""

    WELL_INFO_DIRECTORY: Final[Path] = Path("rms/input/well_modelling/well_info")
    RMS_ECLIPSE_CSV_PATH: Final[Path] = WELL_INFO_DIRECTORY / "rms_eclipse.csv"
    RMS_SIMULATOR_MAPPINGS_CSV_PATH: Final[Path] = (
        WELL_INFO_DIRECTORY / "rms_simulator_mappings.csv"
    )
    RMS_SIMULATOR_RENAMING_TABLE_PATH: Final[Path] = (
        WELL_INFO_DIRECTORY / "rms_simulator.renaming_table"
    )
    RMS_PDM_RENAMING_TABLE_PATH: Final[Path] = (
        WELL_INFO_DIRECTORY / "rms_pdm.renaming_table"
    )

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

    def list_internal_wellbore_mappings(self: Self) -> InternalWellboreMappings:
        """Get all the internal wellbore mappings in the FMU directory."""
        return self._fmu_dir.mappings.internal_wellbore_mappings

    def update_internal_wellbore_mappings(
        self: Self, wellbore_mappings: InternalWellboreMappings
    ) -> InternalWellboreMappings:
        """Save internal wellbore mappings to the mappings resource.

        All existing internal wellbore mappings will be overwritten.
        """
        return self._fmu_dir.mappings.update_internal_wellbore_mappings(
            wellbore_mappings
        )

    def import_rms_eclipse_csv(
        self: Self, relative_path: str | Path | None = None
    ) -> InternalWellboreMappings:
        """Import RMS-to-simulator wellbore mappings from an rms_eclipse CSV file."""
        self._fmu_dir._lock.ensure_can_write()
        wellbore_mappings = self._wellbore_mappings_file_io.read_rms_eclipse_csv(
            relative_path or self.RMS_ECLIPSE_CSV_PATH
        )
        return self._fmu_dir.mappings.update_internal_wellbore_mappings(
            wellbore_mappings
        )

    def export_rms_simulator_csv(
        self: Self, relative_path: str | Path | None = None
    ) -> None:
        """Export RMS-to-simulator wellbore mappings as a CSV file."""
        self._fmu_dir._lock.ensure_can_write()
        filtered_wellbore_mappings = self._filter_wellbore_mappings(
            wellbore_mappings=self.list_internal_wellbore_mappings(),
            source_system=DataSystem.rms,
            target_system=DataSystem.simulator,
            relation_type=InternalRelationType.primary,
        )
        if not filtered_wellbore_mappings:
            raise ValueError(
                "No rms-to-simulator primary wellbore mappings available to export "
                "as rms_simulator_mappings.csv"
            )
        self._wellbore_mappings_file_io.write_rms_simulator_csv(
            filtered_wellbore_mappings,
            relative_path or self.RMS_SIMULATOR_MAPPINGS_CSV_PATH,
        )

    def export_rms_simulator_renaming_table(
        self: Self, relative_path: str | Path | None = None
    ) -> None:
        """Export RMS-to-simulator wellbore mappings as rms_simulator renaming table."""
        self._fmu_dir._lock.ensure_can_write()
        filtered_wellbore_mappings = self._filter_wellbore_mappings(
            wellbore_mappings=self.list_internal_wellbore_mappings(),
            source_system=DataSystem.rms,
            target_system=DataSystem.simulator,
            relation_type=InternalRelationType.primary,
        )
        if not filtered_wellbore_mappings:
            raise ValueError(
                "No rms-to-simulator primary wellbore mappings available to export "
                "as rms_simulator.renaming_table"
            )
        self._wellbore_mappings_file_io.write_wellbore_renaming_table(
            wellbore_mappings=filtered_wellbore_mappings,
            source_system=DataSystem.rms,
            target_system=DataSystem.simulator,
            relative_path=(relative_path or self.RMS_SIMULATOR_RENAMING_TABLE_PATH),
        )

    def export_rms_pdm_renaming_table(
        self: Self, relative_path: str | Path | None = None
    ) -> None:
        """Export RMS-to-PDM wellbore mappings as rms_pdm renaming table."""
        self._fmu_dir._lock.ensure_can_write()
        filtered_wellbore_mappings = self._filter_wellbore_mappings(
            wellbore_mappings=self.list_internal_wellbore_mappings(),
            source_system=DataSystem.rms,
            target_system=DataSystem.pdm,
            relation_type=InternalRelationType.primary,
        )
        if not filtered_wellbore_mappings:
            raise ValueError(
                "No rms-to-pdm primary wellbore mappings available to export as "
                "rms_pdm.renaming_table"
            )
        self._wellbore_mappings_file_io.write_wellbore_renaming_table(
            wellbore_mappings=filtered_wellbore_mappings,
            source_system=DataSystem.rms,
            target_system=DataSystem.pdm,
            relative_path=relative_path or self.RMS_PDM_RENAMING_TABLE_PATH,
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
        mappings_model, list_mappings, _ = (
            self._resolve_internal_mapping_implementation(mapping_type)
        )
        try:
            mappings_for_mapping_type = list_mappings()
        except FileNotFoundError:
            mappings_for_mapping_type = mappings_model.model_validate([])

        filtered_mappings = mappings_model.model_validate(
            [
                mapping
                for mapping in mappings_for_mapping_type
                if mapping.source_system == source_system
            ]
        )
        return InternalMappings(
            **{mapping_type.value: filtered_mappings}  # type: ignore[arg-type]
        )

    def update_internal_mappings_by_source_system(
        self,
        mapping_type: MappingType,
        source_system: DataSystem,
        mappings: InternalStratigraphyMappings | InternalWellboreMappings,
    ) -> None:
        """Replace internal mappings for a specific mapping type and source system.

        Raises:
            ValueError: If mapping type is unsupported
        """
        (
            mappings_model,
            list_mappings,
            update_mappings,
        ) = self._resolve_internal_mapping_implementation(mapping_type)
        if not isinstance(mappings, mappings_model):
            raise ValueError(
                f"Invalid mappings payload for mapping type '{mapping_type.value}'"
            )

        if any(mapping.source_system != source_system for mapping in mappings):
            raise ValueError(
                "All mappings in the request body must use the requested "
                f"source system '{source_system.value}'"
            )

        try:
            existing_mappings_for_mapping_type = list_mappings()
        except FileNotFoundError:
            existing_mappings_for_mapping_type = mappings_model.model_validate([])

        existing_mappings_for_other_source_systems = [
            mapping
            for mapping in existing_mappings_for_mapping_type
            if mapping.source_system != source_system
        ]
        updated_mappings_for_mapping_type = mappings_model.model_validate(
            [*mappings, *existing_mappings_for_other_source_systems]
        )
        update_mappings(updated_mappings_for_mapping_type)

    def _resolve_internal_mapping_implementation(
        self,
        mapping_type: MappingType,
    ) -> tuple[
        type[InternalStratigraphyMappings] | type[InternalWellboreMappings],
        Callable[[], AnyInternalMappings],
        Callable[[AnyInternalMappings], AnyInternalMappings],
    ]:
        """Resolve the model and read/write methods for a mapping type.

        Returns:
            A tuple with the mappings model, list method, and update method.
        """
        if mapping_type == MappingType.stratigraphy:
            return (
                InternalStratigraphyMappings,
                self.list_internal_stratigraphy_mappings,
                lambda mappings: self.update_internal_stratigraphy_mappings(
                    cast("InternalStratigraphyMappings", mappings)
                ),
            )

        if mapping_type == MappingType.wellbore:
            return (
                InternalWellboreMappings,
                self.list_internal_wellbore_mappings,
                lambda mappings: self.update_internal_wellbore_mappings(
                    cast("InternalWellboreMappings", mappings)
                ),
            )

        raise ValueError(  # pragma: no cover
            f"Mapping type '{mapping_type}' is not yet supported"
        )
