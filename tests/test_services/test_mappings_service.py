"""Tests for the MappingsService."""

from unittest.mock import Mock

import pytest
from fmu.datamodels.context.mappings import (
    DataSystem,
    MappingType,
    StratigraphyMappings,
)
from fmu.settings._fmu_dir import ProjectFMUDirectory

from fmu_settings_api.services.mappings import MappingsService


@pytest.fixture
def mappings_service(fmu_dir: ProjectFMUDirectory) -> MappingsService:
    """Returns a MappingsService instance."""
    return MappingsService(fmu_dir)


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
