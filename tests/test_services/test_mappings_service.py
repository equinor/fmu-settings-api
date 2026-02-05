"""Tests for the MappingsService."""

from unittest.mock import Mock

import pytest
from fmu.datamodels.context.mappings import (
    DataSystem,
    MappingType,
    RelationType,
    StratigraphyIdentifierMapping,
    StratigraphyMappings,
)
from fmu.settings._fmu_dir import ProjectFMUDirectory
from pydantic import ValidationError

from fmu_settings_api.services.mappings import MappingsService


@pytest.fixture
def mappings_service(fmu_dir: ProjectFMUDirectory) -> MappingsService:
    """Returns a MappingsService instance."""
    return MappingsService(fmu_dir)


def _make_stratigraphy_mapping(
    source_id: str,
    target_id: str,
    relation_type: RelationType,
) -> StratigraphyIdentifierMapping:
    return StratigraphyIdentifierMapping(
        source_system=DataSystem.rms,
        target_system=DataSystem.smda,
        relation_type=relation_type,
        source_id=source_id,
        target_id=target_id,
        target_uuid=None,
    )


def test_update_mappings_by_systems_mapping_type_mismatch(
    mappings_service: MappingsService,
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test that mapping type mismatch in body raises ValueError."""
    fmu_dir.mappings.update_stratigraphy_mappings(StratigraphyMappings(root=[]))

    wrong_type_mapping = Mock()
    wrong_type_mapping.mapping_type = "wells"
    wrong_type_mapping.source_system = DataSystem.rms
    wrong_type_mapping.target_system = DataSystem.smda

    with pytest.raises(ValueError, match="Mapping type mismatch"):
        mappings_service.update_mappings_by_systems(
            MappingType.stratigraphy,
            DataSystem.rms,
            DataSystem.smda,
            [wrong_type_mapping],
        )


def test_update_mappings_by_systems_source_system_mismatch(
    mappings_service: MappingsService,
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test that source system mismatch in body raises ValueError."""
    fmu_dir.mappings.update_stratigraphy_mappings(StratigraphyMappings(root=[]))

    wrong_target_mapping = Mock()
    wrong_target_mapping.mapping_type = MappingType.stratigraphy
    wrong_target_mapping.source_system = DataSystem.rms
    wrong_target_mapping.target_system = DataSystem.fmu

    with pytest.raises(ValueError, match="Source system mismatch"):
        mappings_service.update_mappings_by_systems(
            MappingType.stratigraphy,
            DataSystem.fmu,
            DataSystem.smda,
            [wrong_target_mapping],
        )


def test_update_mappings_by_systems_target_system_mismatch(
    mappings_service: MappingsService,
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test that target system mismatch in body raises ValueError."""
    fmu_dir.mappings.update_stratigraphy_mappings(StratigraphyMappings(root=[]))

    wrong_target_mapping = Mock()
    wrong_target_mapping.mapping_type = MappingType.stratigraphy
    wrong_target_mapping.source_system = DataSystem.rms
    wrong_target_mapping.target_system = DataSystem.fmu

    with pytest.raises(ValueError, match="Target system mismatch"):
        mappings_service.update_mappings_by_systems(
            MappingType.stratigraphy,
            DataSystem.rms,
            DataSystem.smda,
            [wrong_target_mapping],
        )


def test_update_mappings_by_systems_mapping_group_validation_error(
    mappings_service: MappingsService,
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test that invalid mapping combinations raises ValidationError."""
    fmu_dir.mappings.update_stratigraphy_mappings(StratigraphyMappings(root=[]))

    target_id = "Viking GP."
    source_id = "Viking Gp."

    # More than one primary mapping is an invalid combination
    primary = _make_stratigraphy_mapping(source_id, target_id, RelationType.primary)
    primary_two = _make_stratigraphy_mapping(
        "VIKING GP", target_id, RelationType.primary
    )
    with pytest.raises(ValidationError, match="1 validation error for MappingGroup"):
        mappings_service.update_mappings_by_systems(
            MappingType.stratigraphy,
            DataSystem.rms,
            DataSystem.smda,
            [primary, primary_two],
        )

    # More than one equivalent mapping is an invalid combination
    equivalent = _make_stratigraphy_mapping(
        source_id, source_id, RelationType.equivalent
    )
    equivalent_two = _make_stratigraphy_mapping(
        source_id, source_id, RelationType.equivalent
    )
    with pytest.raises(ValidationError, match="1 validation error for MappingGroup"):
        mappings_service.update_mappings_by_systems(
            MappingType.stratigraphy,
            DataSystem.rms,
            DataSystem.smda,
            [equivalent, equivalent_two],
        )

    # Alias mapping without primary mapping is an invalid combination
    alias = _make_stratigraphy_mapping("Viking gp", target_id, RelationType.alias)
    with pytest.raises(ValidationError, match="1 validation error for MappingGroup"):
        mappings_service.update_mappings_by_systems(
            MappingType.stratigraphy,
            DataSystem.rms,
            DataSystem.smda,
            [alias],
        )

    # Duplicate mappings is an invalid combination
    primary = _make_stratigraphy_mapping(source_id, target_id, RelationType.primary)
    alias_to_duplicate = _make_stratigraphy_mapping(
        "Viking gp", target_id, RelationType.alias
    )
    with pytest.raises(ValidationError, match="1 validation error for MappingGroup"):
        mappings_service.update_mappings_by_systems(
            MappingType.stratigraphy,
            DataSystem.rms,
            DataSystem.smda,
            [primary, alias, alias_to_duplicate],
        )
