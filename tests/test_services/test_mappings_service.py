"""Tests for the MappingsService."""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import PropertyMock, patch

import pytest
from fmu.datamodels.context.mappings import DataSystem, MappingType
from fmu.settings import (
    InternalMappings,
    InternalRelationType,
    InternalStratigraphyIdentifierMapping,
    InternalStratigraphyMappings,
    InternalWellboreIdentifierMapping,
    InternalWellboreMappings,
    ProjectFMUDirectory,
)

from fmu_settings_api.services.mappings import MappingsService


@pytest.fixture
def mappings_service(fmu_dir: ProjectFMUDirectory) -> MappingsService:
    """Returns a MappingsService instance."""
    return MappingsService(fmu_dir)


def test_get_internal_mappings_by_source_system_returns_filtered_stratigraphy(
    mappings_service: MappingsService,
    fmu_dir: ProjectFMUDirectory,
    make_stratigraphy_mapping: Callable[..., InternalStratigraphyIdentifierMapping],
) -> None:
    """Test filtered read returns mappings for the requested source system."""
    stratigraphy_mappings = InternalStratigraphyMappings(
        root=[
            make_stratigraphy_mapping(
                "TopVolantis",
                "TopVolantis",
                InternalRelationType.primary,
                source_system=DataSystem.rms,
                target_system=DataSystem.rms,
            ),
            make_stratigraphy_mapping(
                "TopVolantis",
                "VOLANTIS GP. Top",
                InternalRelationType.primary,
                source_system=DataSystem.rms,
                target_system=DataSystem.smda,
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
    fmu_dir.mappings.update_internal_stratigraphy_mappings(stratigraphy_mappings)

    assert mappings_service.get_internal_mappings_by_source_system(
        MappingType.stratigraphy,
        DataSystem.rms,
    ) == InternalMappings(
        stratigraphy=InternalStratigraphyMappings(
            root=[
                stratigraphy_mappings[0],
                stratigraphy_mappings[1],
            ]
        )
    )


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


def test_import_rms_eclipse_csv_updates_wellbore_mappings(
    mappings_service: MappingsService,
    fmu_dir: ProjectFMUDirectory,
    make_rms_simulator_mappings: Callable[[], InternalWellboreMappings],
) -> None:
    """Test importing delegates to file IO and persists the returned mappings."""
    csv_relative_path = Path("data/custom/rms_eclipse.csv")
    imported_mappings = make_rms_simulator_mappings()
    stored_mappings = InternalWellboreMappings(root=list(imported_mappings.root))

    with (
        patch.object(
            mappings_service._wellbore_mappings_file_io,
            "read_rms_eclipse_csv",
            return_value=imported_mappings,
        ) as read_mock,
        patch.object(
            fmu_dir.mappings,
            "update_internal_wellbore_mappings",
            return_value=stored_mappings,
        ) as update_mock,
    ):
        assert (
            mappings_service.import_rms_eclipse_csv(csv_relative_path)
            == stored_mappings
        )

    read_mock.assert_called_once_with(csv_relative_path)
    update_mock.assert_called_once_with(imported_mappings)


def test_export_rms_eclipse_csv_returns_exported_path(
    mappings_service: MappingsService,
    fmu_dir: ProjectFMUDirectory,
    make_rms_simulator_mappings: Callable[[], InternalWellboreMappings],
    make_wellbore_mapping: Callable[..., InternalWellboreIdentifierMapping],
) -> None:
    """Test CSV export forwards stored mappings and path to the file interface."""
    expected_path = Path("data/custom/rms_eclipse.csv")
    stored_mappings = make_rms_simulator_mappings()
    filtered_mappings = [make_wellbore_mapping()]

    with (
        patch.object(
            type(fmu_dir.mappings),
            "internal_wellbore_mappings",
            new_callable=PropertyMock,
        ) as mappings_mock,
        patch.object(
            mappings_service._wellbore_mappings_file_io,
            "write_rms_eclipse_csv",
            return_value=expected_path,
        ) as write_mock,
    ):
        mappings_mock.return_value = stored_mappings
        assert mappings_service.export_rms_eclipse_csv(expected_path) == expected_path

    write_mock.assert_called_once_with(filtered_mappings, expected_path)


def test_export_rms_eclipse_renaming_table_returns_exported_path(
    mappings_service: MappingsService,
    fmu_dir: ProjectFMUDirectory,
    make_rms_simulator_mappings: Callable[[], InternalWellboreMappings],
    make_wellbore_mapping: Callable[..., InternalWellboreIdentifierMapping],
) -> None:
    """Test RMS renaming-table export forwards stored mappings and path."""
    expected_path = Path("data/custom/rms_eclipse.renaming_table")
    stored_mappings = make_rms_simulator_mappings()
    filtered_mappings = [make_wellbore_mapping()]

    with (
        patch.object(
            type(fmu_dir.mappings),
            "internal_wellbore_mappings",
            new_callable=PropertyMock,
        ) as mappings_mock,
        patch.object(
            mappings_service._wellbore_mappings_file_io,
            "write_rms_eclipse_renaming_table",
            return_value=expected_path,
        ) as write_mock,
    ):
        mappings_mock.return_value = stored_mappings
        assert (
            mappings_service.export_rms_eclipse_renaming_table(expected_path)
            == expected_path
        )

    write_mock.assert_called_once_with(filtered_mappings, expected_path)


def test_export_pdm_rms_renaming_table_returns_exported_path(
    mappings_service: MappingsService,
    fmu_dir: ProjectFMUDirectory,
    make_wellbore_mapping: Callable[..., InternalWellboreIdentifierMapping],
) -> None:
    """Test PDM-to-RMS export forwards stored mappings and path."""
    expected_path = Path("data/custom/pdm_rms.renaming_table")
    stored_mappings = InternalWellboreMappings(
        root=[
            make_wellbore_mapping(
                source_system=DataSystem.pdm,
                target_system=DataSystem.pdm,
                source_id="30/9-B-43 A",
                target_id="30/9-B-43 A",
            ),
            make_wellbore_mapping(
                source_system=DataSystem.pdm,
                target_system=DataSystem.rms,
                source_id="30/9-B-43 A",
                target_id="30_9-B-43_A",
            ),
        ]
    )
    filtered_mappings = [stored_mappings[1]]

    with (
        patch.object(
            type(fmu_dir.mappings),
            "internal_wellbore_mappings",
            new_callable=PropertyMock,
        ) as mappings_mock,
        patch.object(
            mappings_service._wellbore_mappings_file_io,
            "write_pdm_rms_renaming_table",
            return_value=expected_path,
        ) as write_mock,
    ):
        mappings_mock.return_value = stored_mappings
        assert (
            mappings_service.export_pdm_rms_renaming_table(expected_path)
            == expected_path
        )

    write_mock.assert_called_once_with(filtered_mappings, expected_path)
