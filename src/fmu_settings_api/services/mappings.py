"""Service for managing mappings in .fmu and business logic."""

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Self

from fmu.datamodels.context.mappings import (
    AnyIdentifierMapping,
    DataSystem,
    MappingType,
    StratigraphyMappings,
)
from fmu.settings import ProjectFMUDirectory
from fmu.settings.models.mappings import MappingGroup

if TYPE_CHECKING:
    from uuid import UUID


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

    def build_mapping_groups(
        self,
        mappings: Iterable[AnyIdentifierMapping],
    ) -> list[MappingGroup]:
        """Build MappingGroup objects from mappings sharing the same target context.

        Groups by target_id, target_uuid (if set), mapping_type, target_system,
        and source_system.
        """
        grouped: defaultdict[
            tuple[str, UUID | None, MappingType, DataSystem, DataSystem],
            list[AnyIdentifierMapping],
        ] = defaultdict(list)

        for mapping in mappings:
            grouped[
                (
                    mapping.target_id,
                    mapping.target_uuid,
                    mapping.mapping_type,
                    mapping.target_system,
                    mapping.source_system,
                )
            ].append(mapping)

        return [
            MappingGroup(
                target_id=group_target_id,
                target_uuid=group_target_uuid,
                mapping_type=group_mapping_type,
                target_system=group_target_system,
                source_system=group_source_system,
                mappings=batch,
            )
            for (
                group_target_id,
                group_target_uuid,
                group_mapping_type,
                group_target_system,
                group_source_system,
            ), batch in grouped.items()
        ]

    def get_mappings_by_systems(
        self,
        mapping_type: MappingType,
        source_system: DataSystem,
        target_system: DataSystem,
    ) -> list[MappingGroup]:
        """Get mappings for specific mapping type, source and target systems.

        Filters mappings by the specified source_system and target_system,
        then groups them by target context (target_id, target_uuid, mapping_type,
        target_system, and source_system).

        Raises:
            ValueError: If mapping type is unsupported
        """
        if mapping_type == MappingType.stratigraphy:
            all_mappings = self.list_stratigraphy_mappings()
        else:
            raise ValueError(f"Mapping type '{mapping_type}' is not yet supported")

        filtered = [
            mapping
            for mapping in all_mappings
            if mapping.source_system == source_system
            and mapping.target_system == target_system
        ]

        return self.build_mapping_groups(filtered)

    def update_mappings_by_systems(
        self,
        mapping_type: MappingType,
        source_system: DataSystem,
        target_system: DataSystem,
        new_mappings: list[AnyIdentifierMapping],
    ) -> None:
        """Update mappings for specific mapping type, source and target systems.

        Replaces all mappings for the specified type/source/target combination
        while preserving mappings for other combinations.

        Validates that:
        - All mappings match the specified mapping_type, source_system,
          and target_system
        - No duplicate mappings (same source_id, source_uuid, target_id,
          target_uuid, and relation_type)
        - Mappings form valid groups (at most one primary per target, all
          mappings share the same target context)

        Raises:
            ValueError: If validation fails or mapping type is unsupported
        """
        seen: set[tuple[str, UUID | None, str, UUID | None, str]] = set()
        for mapping in new_mappings:
            if mapping.mapping_type != mapping_type:
                raise ValueError(
                    f"Mapping type mismatch: expected '{mapping_type}' but "
                    f"found '{mapping.mapping_type}'"
                )
            if mapping.source_system != source_system:
                raise ValueError(
                    f"Source system mismatch: expected '{source_system}' but "
                    f"found '{mapping.source_system}'"
                )
            if mapping.target_system != target_system:
                raise ValueError(
                    f"Target system mismatch: expected '{target_system}' but "
                    f"found '{mapping.target_system}'"
                )

            key = (
                mapping.source_id,
                mapping.source_uuid,
                mapping.target_id,
                mapping.target_uuid,
                mapping.relation_type.value,
            )
            if key in seen:
                raise ValueError(
                    f"Duplicate mapping found: source_id='{mapping.source_id}', "
                    f"source_uuid='{mapping.source_uuid}', "
                    f"target_id='{mapping.target_id}', "
                    f"target_uuid='{mapping.target_uuid}', "
                    f"relation_type='{mapping.relation_type.value}'"
                )
            seen.add(key)

        self.build_mapping_groups(new_mappings)

        if mapping_type == MappingType.stratigraphy:
            all_mappings = self.list_stratigraphy_mappings()

            other_mappings = [
                mapping
                for mapping in all_mappings
                if not (
                    mapping.source_system == source_system
                    and mapping.target_system == target_system
                )
            ]

            updated_mappings = StratigraphyMappings(root=other_mappings + new_mappings)
            self.update_stratigraphy_mappings(updated_mappings)
        else:
            raise ValueError(f"Mapping type '{mapping_type}' is not yet supported")
