"""Tests for the MappingsService."""

from collections.abc import Callable
from unittest.mock import patch

import pytest
from fmu.datamodels.context.mappings import (
    DataSystem,
    MappingType,
)
from fmu.settings import (
    InternalMappings,
    InternalRelationType,
    InternalStratigraphyIdentifierMapping,
    InternalStratigraphyMappings,
    ProjectFMUDirectory,
)

from fmu_settings_api.services.mappings import MappingsService


@pytest.fixture
def mappings_service(fmu_dir: ProjectFMUDirectory) -> MappingsService:
    """Returns a MappingsService instance."""
    return MappingsService(fmu_dir)


def test_get_internal_mappings_by_source_system_unsupported_type(
    mappings_service: MappingsService,
) -> None:
    """Test unsupported mapping types raise ValueError on filtered read."""
    with pytest.raises(ValueError, match="not yet supported"):
        mappings_service.get_internal_mappings_by_source_system(
            MappingType.wellbore,
            DataSystem.rms,
        )


def test_get_internal_mappings_by_source_system_returns_empty_when_missing(
    mappings_service: MappingsService,
) -> None:
    """Test missing mappings file returns an empty mappings model."""
    with patch.object(
        mappings_service,
        "list_internal_stratigraphy_mappings",
        side_effect=FileNotFoundError("Mappings file not found"),
    ):
        assert mappings_service.get_internal_mappings_by_source_system(
            MappingType.stratigraphy,
            DataSystem.rms,
        ) == InternalMappings(stratigraphy=InternalStratigraphyMappings(root=[]))


def test_update_internal_mappings_by_source_system_replaces_existing_stratigraphy(
    mappings_service: MappingsService,
    fmu_dir: ProjectFMUDirectory,
    make_stratigraphy_mapping: Callable[..., InternalStratigraphyIdentifierMapping],
) -> None:
    """Test updates replace only the stored stratigraphy source partition."""
    initial_mappings = InternalStratigraphyMappings(
        root=[
            make_stratigraphy_mapping(
                "TopVolantis",
                "TopVolantis",
                InternalRelationType.primary,
                source_system=DataSystem.rms,
                target_system=DataSystem.rms,
            ),
            make_stratigraphy_mapping(
                "TopHugin",
                "TopHugin",
                InternalRelationType.primary,
                source_system=DataSystem.simulator,
                target_system=DataSystem.simulator,
            ),
            make_stratigraphy_mapping(
                "TopHugin",
                "HUGIN GP. Top",
                InternalRelationType.primary,
                source_system=DataSystem.simulator,
                target_system=DataSystem.smda,
            ),
        ]
    )
    replacement_mappings = InternalStratigraphyMappings(
        root=[
            make_stratigraphy_mapping(
                "TopViking",
                "TopViking",
                InternalRelationType.primary,
                source_system=DataSystem.rms,
                target_system=DataSystem.rms,
            ),
            make_stratigraphy_mapping(
                "TopViking",
                "VIKING GP. Top",
                InternalRelationType.primary,
                source_system=DataSystem.rms,
                target_system=DataSystem.smda,
            ),
        ]
    )

    fmu_dir.mappings.update_internal_stratigraphy_mappings(initial_mappings)

    mappings_service.update_internal_mappings_by_source_system(
        MappingType.stratigraphy,
        DataSystem.rms,
        replacement_mappings,
    )

    assert (
        fmu_dir.mappings.internal_stratigraphy_mappings
        == InternalStratigraphyMappings(
            root=[
                replacement_mappings[0],
                replacement_mappings[1],
                initial_mappings[1],
                initial_mappings[2],
            ]
        )
    )


def test_update_internal_mappings_by_source_system_creates_mappings_file_if_missing(
    mappings_service: MappingsService,
    fmu_dir: ProjectFMUDirectory,
    make_stratigraphy_mapping: Callable[..., InternalStratigraphyIdentifierMapping],
) -> None:
    """Test first-time mapping updates create mappings.json instead of failing."""
    mappings_path = fmu_dir.mappings.path
    assert not mappings_path.exists()

    primary = make_stratigraphy_mapping(
        "TopVolantis",
        "TopVolantis",
        InternalRelationType.primary,
        source_system=DataSystem.rms,
        target_system=DataSystem.rms,
    )
    cross_system = make_stratigraphy_mapping(
        "TopVolantis",
        "VOLANTIS GP. Top",
        InternalRelationType.primary,
        source_system=DataSystem.rms,
        target_system=DataSystem.smda,
    )
    mappings = InternalStratigraphyMappings(root=[primary, cross_system])

    mappings_service.update_internal_mappings_by_source_system(
        MappingType.stratigraphy,
        DataSystem.rms,
        mappings,
    )

    assert mappings_path.exists()
    assert fmu_dir.mappings.internal_stratigraphy_mappings == mappings


def test_update_internal_mappings_by_source_system_supports_unmappable(
    mappings_service: MappingsService,
    fmu_dir: ProjectFMUDirectory,
    make_stratigraphy_mapping: Callable[..., InternalStratigraphyIdentifierMapping],
) -> None:
    """Test source partition updates support unmappable cross-system mappings."""
    primary = make_stratigraphy_mapping(
        "TopUnmapped",
        "TopUnmapped",
        InternalRelationType.primary,
        source_system=DataSystem.rms,
        target_system=DataSystem.rms,
    )
    unmappable = make_stratigraphy_mapping(
        "TopUnmapped",
        None,
        InternalRelationType.unmappable,
        source_system=DataSystem.rms,
        target_system=DataSystem.smda,
    )
    mappings = InternalStratigraphyMappings(root=[primary, unmappable])

    mappings_service.update_internal_mappings_by_source_system(
        MappingType.stratigraphy,
        DataSystem.rms,
        mappings,
    )

    assert fmu_dir.mappings.internal_stratigraphy_mappings == mappings
    assert mappings_service.get_internal_mappings_by_source_system(
        MappingType.stratigraphy, DataSystem.rms
    ) == InternalMappings(stratigraphy=mappings)


def test_update_internal_mappings_by_source_system_unsupported_type(
    mappings_service: MappingsService,
) -> None:
    """Test unsupported mapping types raise ValueError on write."""
    with pytest.raises(ValueError, match="not yet supported"):
        mappings_service.update_internal_mappings_by_source_system(
            MappingType.wellbore,
            DataSystem.rms,
            InternalStratigraphyMappings(root=[]),
        )


def test_update_internal_mappings_by_source_system_rejects_mismatched_source_system(
    mappings_service: MappingsService,
    make_stratigraphy_mapping: Callable[..., InternalStratigraphyIdentifierMapping],
) -> None:
    """Test updates reject mappings outside the requested source partition."""
    mismatched_mappings = InternalStratigraphyMappings(
        root=[
            make_stratigraphy_mapping(
                "TopHugin",
                "TopHugin",
                InternalRelationType.primary,
                source_system=DataSystem.simulator,
                target_system=DataSystem.simulator,
            )
        ]
    )

    with pytest.raises(ValueError, match="requested source system 'rms'"):
        mappings_service.update_internal_mappings_by_source_system(
            MappingType.stratigraphy,
            DataSystem.rms,
            mismatched_mappings,
        )
