"""Tests for ProjectValidationService."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, call
from uuid import UUID

import pytest
from fmu.datamodels.common import Smda
from fmu.settings import ProjectFMUDirectory
from fmu.settings.models.project_config import (
    RmsHorizon,
    RmsStratigraphicZone,
    RmsWell,
)

from fmu_settings_api.models.smda import SmdaMasterdataResult, SmdaSelectedField
from fmu_settings_api.services.project_validation import (
    MasterdataSmdaMismatchError,
    ProjectValidationService,
    RmsProjectMismatchError,
)


def _set_rms_config(
    fmu_dir: ProjectFMUDirectory,
    *,
    version: str = "14.2.2",
    horizons: list[RmsHorizon] | None = None,
    zones: list[RmsStratigraphicZone] | None = None,
    wells: list[RmsWell] | None = None,
) -> None:
    """Save RMS configuration used by validation tests."""
    fmu_dir.set_config_value(
        "rms",
        {
            "path": Path("/path/to/project.rms14.2.2"),
            "version": version,
            "horizons": (
                None
                if horizons is None
                else [horizon.model_dump() for horizon in horizons]
            ),
            "zones": None if zones is None else [zone.model_dump() for zone in zones],
            "wells": None if wells is None else [well.model_dump() for well in wells],
        },
    )


def _smda_result_from_saved(
    saved_smda: Smda,
    overrides: dict[str, Any] | None = None,
) -> SmdaMasterdataResult:
    """Create an SMDA masterdata result from saved SMDA config."""
    data = {
        "field": saved_smda.field,
        "country": saved_smda.country,
        "discovery": saved_smda.discovery,
        "stratigraphic_columns": [saved_smda.stratigraphic_column],
        "field_coordinate_system": saved_smda.coordinate_system,
        "coordinate_systems": [saved_smda.coordinate_system],
    }
    if overrides is not None:
        data.update(overrides)
    return SmdaMasterdataResult.model_validate(data)


async def test_validate_masterdata_smda_updates_validation_metadata(
    fmu_dir: ProjectFMUDirectory,
    smda_masterdata: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test successful SMDA masterdata validation updates validation metadata."""
    fmu_dir.set_config_value("masterdata.smda", smda_masterdata)
    saved_config = fmu_dir.config.load()
    assert saved_config.masterdata is not None
    saved_smda = saved_config.masterdata.smda
    smda_service = Mock()
    smda_service.get_masterdata = AsyncMock(
        return_value=_smda_result_from_saved(saved_smda)
    )
    monkeypatch.setattr(
        "fmu.settings._fmu_dir.getpass.getuser",
        lambda: "test-user",
    )

    await ProjectValidationService(
        fmu_dir
    ).validate_masterdata_against_smda_and_update_metadata(smda_service)

    config = fmu_dir.config.load(force=True)
    assert config.validation.masterdata_smda is not None
    assert config.validation.masterdata_smda.last_validated_at is not None
    assert config.validation.masterdata_smda.last_validated_by == "test-user"
    smda_service.get_masterdata.assert_awaited_once_with(
        [
            SmdaSelectedField(
                identifier=saved_smda.field[0].identifier,
                uuid=saved_smda.field[0].uuid,
            )
        ]
    )


async def test_validate_masterdata_smda_validates_each_saved_field(
    fmu_dir: ProjectFMUDirectory,
    smda_masterdata: dict[str, Any],
) -> None:
    """Test validation fetches current SMDA masterdata for every saved field."""
    smda_masterdata["field"].append(
        {
            "identifier": "OtherField",
            "uuid": "25ce3b84-766f-4c93-9050-b154861f9100",
        }
    )
    fmu_dir.set_config_value("masterdata.smda", smda_masterdata)
    saved_config = fmu_dir.config.load()
    assert saved_config.masterdata is not None
    saved_smda = saved_config.masterdata.smda
    masterdata_by_field = {
        field.identifier: _smda_result_from_saved(saved_smda, {"field": [field]})
        for field in saved_smda.field
    }
    smda_service = Mock()
    smda_service.get_masterdata = AsyncMock(
        side_effect=lambda fields: masterdata_by_field[fields[0].identifier]
    )

    await ProjectValidationService(
        fmu_dir
    ).validate_masterdata_against_smda_and_update_metadata(smda_service)

    assert smda_service.get_masterdata.await_args_list == [
        call([SmdaSelectedField(identifier=field.identifier, uuid=field.uuid)])
        for field in saved_smda.field
    ]
    assert fmu_dir.config.load(force=True).validation.masterdata_smda is not None


async def test_validate_masterdata_smda_allows_extra_current_values(
    fmu_dir: ProjectFMUDirectory,
    smda_masterdata: dict[str, Any],
) -> None:
    """Test validation accepts saved SMDA list values in any current order."""
    extra_field = {
        "identifier": "OtherField",
        "uuid": "25ce3b84-766f-4c93-9050-b154861f9100",
    }
    extra_country = {
        "identifier": "Brazil",
        "uuid": "35ce3b84-766f-4c93-9050-b154861f9100",
    }
    extra_discovery = {
        "short_identifier": "OtherDiscovery",
        "uuid": "45ce3b84-766f-4c93-9050-b154861f9100",
    }
    smda_masterdata["field"].append(extra_field)
    smda_masterdata["country"].append(extra_country)
    smda_masterdata["discovery"].append(extra_discovery)
    fmu_dir.set_config_value("masterdata.smda", smda_masterdata)
    saved_config = fmu_dir.config.load()
    assert saved_config.masterdata is not None
    saved_smda = saved_config.masterdata.smda
    current_extra_field = saved_smda.field[0].model_copy(
        update={
            "identifier": "CurrentExtraField",
            "uuid": UUID("55ce3b84-766f-4c93-9050-b154861f9100"),
        }
    )

    smda_service = Mock()
    smda_service.get_masterdata = AsyncMock(
        return_value=_smda_result_from_saved(
            saved_smda,
            {
                "field": list(reversed([*saved_smda.field, current_extra_field])),
                "country": list(reversed(saved_smda.country)),
                "discovery": list(reversed(saved_smda.discovery)),
            },
        )
    )

    await ProjectValidationService(
        fmu_dir
    ).validate_masterdata_against_smda_and_update_metadata(smda_service)

    assert fmu_dir.config.load(force=True).validation.masterdata_smda is not None


async def test_validate_masterdata_smda_raises_for_mismatch(
    fmu_dir: ProjectFMUDirectory,
    smda_masterdata: dict[str, Any],
) -> None:
    """Test validation raises mismatch details when saved masterdata differs."""
    fmu_dir.set_config_value("masterdata.smda", smda_masterdata)
    saved_config = fmu_dir.config.load()
    assert saved_config.masterdata is not None
    saved_smda = saved_config.masterdata.smda
    current_field = saved_smda.field[0].model_copy(update={"identifier": "Changed"})
    smda_service = Mock()
    smda_service.get_masterdata = AsyncMock(
        return_value=_smda_result_from_saved(saved_smda, {"field": [current_field]})
    )

    with pytest.raises(MasterdataSmdaMismatchError) as exc_info:
        await ProjectValidationService(
            fmu_dir
        ).validate_masterdata_against_smda_and_update_metadata(smda_service)

    assert isinstance(exc_info.value, ValueError)
    assert exc_info.value.mismatches[0].key == "masterdata.smda.field"
    assert exc_info.value.mismatches[0].saved_value == [
        saved_smda.field[0].model_dump(mode="json")
    ]
    assert exc_info.value.mismatches[0].source_value == [
        current_field.model_dump(mode="json")
    ]
    assert fmu_dir.config.load(force=True).validation.masterdata_smda is None


async def test_validate_masterdata_smda_raises_when_masterdata_is_missing(
    fmu_dir: ProjectFMUDirectory,
    smda_masterdata: dict[str, Any],
) -> None:
    """Test validation requires saved project masterdata."""
    saved_smda = Smda.model_validate(smda_masterdata)
    smda_service = Mock()
    smda_service.get_masterdata = AsyncMock(
        return_value=_smda_result_from_saved(saved_smda)
    )

    with pytest.raises(
        ValueError,
        match="Project masterdata must be set before validating against SMDA.",
    ):
        await ProjectValidationService(
            fmu_dir
        ).validate_masterdata_against_smda_and_update_metadata(smda_service)


def test_validate_rms_project_updates_validation_metadata(
    fmu_dir: ProjectFMUDirectory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test successful RMS validation records the user, time, and source reads."""
    horizon = RmsHorizon(name="Top", type="interpreted")
    zone = RmsStratigraphicZone(
        name="Reservoir",
        top_horizon_name="Top",
        base_horizon_name="Base",
        stratigraphic_column_name=["Column"],
    )
    well = RmsWell(name="A-1", planned=True)
    _set_rms_config(fmu_dir, horizons=[horizon], zones=[zone], wells=[well])

    rms_service = Mock()
    rms_service.get_rms_version.return_value = "14.2.2"
    rms_service.get_horizons.return_value = [horizon]
    rms_service.get_zones.return_value = [zone]
    rms_service.get_wells.return_value = [well.model_copy(update={"planned": False})]
    monkeypatch.setattr(
        "fmu.settings._fmu_dir.getpass.getuser",
        lambda: "test-user",
    )

    ProjectValidationService(fmu_dir).validate_rms_project_and_update_metadata(
        rms_service, Mock()
    )

    record = fmu_dir.config.load(force=True).validation.rms_project
    assert record is not None
    assert record.last_validated_at.tzinfo is not None
    assert record.last_validated_at.utcoffset() is not None
    assert record.last_validated_by == "test-user"
    rms_service.get_rms_version.assert_called_once_with(
        Path("/path/to/project.rms14.2.2")
    )
    rms_service.get_horizons.assert_called_once()
    rms_service.get_zones.assert_called_once()
    rms_service.get_wells.assert_called_once()
    rms_service.get_coordinate_system.assert_not_called()


def test_validate_rms_project_accepts_equal_saved_and_current_items(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test equal saved and current RMS items pass without mismatches."""
    horizons = [RmsHorizon(name="Top", type="interpreted")]
    zones = [
        RmsStratigraphicZone(
            name="Reservoir",
            top_horizon_name="Top",
            base_horizon_name="Base",
            stratigraphic_column_name=["Column"],
        )
    ]
    wells = [RmsWell(name="A-1", planned=True)]
    _set_rms_config(
        fmu_dir,
        horizons=horizons,
        zones=zones,
        wells=wells,
    )
    rms_service = Mock()
    rms_service.get_rms_version.return_value = "14.2.2"
    rms_service.get_horizons.return_value = horizons
    rms_service.get_zones.return_value = zones
    rms_service.get_wells.return_value = wells

    ProjectValidationService(fmu_dir).validate_rms_project_and_update_metadata(
        rms_service, Mock()
    )

    assert fmu_dir.config.load(force=True).validation.rms_project is not None


def test_validate_rms_project_accepts_configured_subsets_in_any_order(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test additional and differently ordered RMS source items are valid."""
    saved_horizons = [
        RmsHorizon(name="Top", type="interpreted"),
        RmsHorizon(name="Base", type="calculated"),
    ]
    saved_zones = [
        RmsStratigraphicZone(
            name="Reservoir",
            top_horizon_name="Top",
            base_horizon_name="Base",
        )
    ]
    saved_wells = [RmsWell(name="A-1")]
    _set_rms_config(
        fmu_dir,
        horizons=saved_horizons,
        zones=saved_zones,
        wells=saved_wells,
    )

    extra_horizon = RmsHorizon(name="Extra", type="calculated")
    extra_zone = RmsStratigraphicZone(
        name="ExtraZone",
        top_horizon_name="Top",
        base_horizon_name="Base",
    )
    rms_service = Mock()
    rms_service.get_rms_version.return_value = "14.2.2"
    rms_service.get_horizons.return_value = [
        extra_horizon,
        saved_horizons[1],
        saved_horizons[0],
    ]
    rms_service.get_zones.return_value = [extra_zone, *saved_zones]
    rms_service.get_wells.return_value = [
        RmsWell(name="ExtraWell"),
        RmsWell(name="A-1", planned=True),
    ]

    ProjectValidationService(fmu_dir).validate_rms_project_and_update_metadata(
        rms_service, Mock()
    )

    assert fmu_dir.config.load(force=True).validation.rms_project is not None


def test_validate_rms_project_reports_all_mismatches(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test version and item mismatches are returned together."""
    saved_horizon = RmsHorizon(name="Top", type="interpreted")
    saved_zone = RmsStratigraphicZone(
        name="Reservoir",
        top_horizon_name="Top",
        base_horizon_name="Base",
        stratigraphic_column_name=["Column"],
    )
    saved_well = RmsWell(name="A-1", planned=True)
    _set_rms_config(
        fmu_dir,
        horizons=[saved_horizon],
        zones=[saved_zone],
        wells=[saved_well],
    )
    current_horizon = saved_horizon.model_copy(update={"type": "calculated"})
    current_zone = saved_zone.model_copy(update={"top_horizon_name": "ChangedTop"})
    rms_service = Mock()
    rms_service.get_rms_version.return_value = "14.3"
    rms_service.get_horizons.return_value = [current_horizon]
    rms_service.get_zones.return_value = [current_zone]
    rms_service.get_wells.return_value = []

    with pytest.raises(RmsProjectMismatchError) as exc_info:
        ProjectValidationService(fmu_dir).validate_rms_project_and_update_metadata(
            rms_service, Mock()
        )

    mismatches = exc_info.value.mismatches
    assert [mismatch.key for mismatch in mismatches] == [
        "rms.version",
        "rms.horizons.Top",
        "rms.zones.Reservoir",
        "rms.wells.A-1",
    ]
    assert [mismatch.message for mismatch in mismatches] == [
        "The RMS version saved in the FMU project does not match the version of "
        "the open RMS project.",
        "RMS horizon 'Top' has different settings in the FMU project and the "
        "open RMS project.",
        "RMS zone 'Reservoir' has different settings in the FMU project and the "
        "open RMS project.",
        "RMS well 'A-1' is saved in the FMU project but is not present in the "
        "open RMS project.",
    ]
    assert mismatches[0].saved_value == "14.2.2"
    assert mismatches[0].source_value == "14.3"
    assert mismatches[1].saved_value == saved_horizon.model_dump(mode="json")
    assert mismatches[1].source_value == current_horizon.model_dump(mode="json")
    assert mismatches[2].saved_value == saved_zone.model_dump(mode="json")
    assert mismatches[2].source_value == current_zone.model_dump(mode="json")
    assert mismatches[3].saved_value == saved_well.model_dump(mode="json")
    assert mismatches[3].source_value is None
    assert fmu_dir.config.load(force=True).validation.rms_project is None


def test_validate_rms_project_reports_missing_horizon_and_zone(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test configured horizons and zones missing from RMS are reported."""
    saved_horizon = RmsHorizon(name="Top", type="interpreted")
    saved_zone = RmsStratigraphicZone(
        name="Reservoir",
        top_horizon_name="Top",
        base_horizon_name="Base",
    )
    _set_rms_config(fmu_dir, horizons=[saved_horizon], zones=[saved_zone])
    rms_service = Mock()
    rms_service.get_rms_version.return_value = "14.2.2"
    rms_service.get_horizons.return_value = []
    rms_service.get_zones.return_value = []

    with pytest.raises(RmsProjectMismatchError) as exc_info:
        ProjectValidationService(fmu_dir).validate_rms_project_and_update_metadata(
            rms_service, Mock()
        )

    mismatches = exc_info.value.mismatches
    assert [mismatch.key for mismatch in mismatches] == [
        "rms.horizons.Top",
        "rms.zones.Reservoir",
    ]
    assert all(mismatch.source_value is None for mismatch in mismatches)


def test_validate_rms_project_does_not_read_unsaved_categories(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test validation does not read categories that are not saved in config."""
    _set_rms_config(fmu_dir)
    rms_service = Mock()
    rms_service.get_rms_version.return_value = "14.2.2"

    ProjectValidationService(fmu_dir).validate_rms_project_and_update_metadata(
        rms_service, Mock()
    )

    rms_service.get_rms_version.assert_called_once()
    rms_service.get_horizons.assert_not_called()
    rms_service.get_zones.assert_not_called()
    rms_service.get_wells.assert_not_called()
    rms_service.get_coordinate_system.assert_not_called()


def test_validate_rms_project_accepts_empty_saved_horizon_zone_and_well_lists(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test validation succeeds when no horizons, zones, or wells are saved."""
    _set_rms_config(fmu_dir, horizons=[], zones=[], wells=[])
    rms_service = Mock()
    rms_service.get_rms_version.return_value = "14.2.2"
    rms_service.get_horizons.return_value = [
        RmsHorizon(name="Extra", type="calculated")
    ]
    rms_service.get_zones.return_value = [
        RmsStratigraphicZone(
            name="ExtraZone",
            top_horizon_name="Top",
            base_horizon_name="Base",
        )
    ]
    rms_service.get_wells.return_value = [RmsWell(name="ExtraWell")]

    ProjectValidationService(fmu_dir).validate_rms_project_and_update_metadata(
        rms_service, Mock()
    )

    assert fmu_dir.config.load(force=True).validation.rms_project is not None


def test_validate_rms_project_requires_rms_configuration(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test missing RMS configuration does not access RMS or write metadata."""
    rms_service = Mock()

    with pytest.raises(
        ValueError,
        match="No RMS settings are saved in the FMU project.",
    ):
        ProjectValidationService(fmu_dir).validate_rms_project_and_update_metadata(
            rms_service, Mock()
        )

    rms_service.get_rms_version.assert_not_called()
    rms_service.get_horizons.assert_not_called()
    rms_service.get_zones.assert_not_called()
    rms_service.get_wells.assert_not_called()
    assert fmu_dir.config.load(force=True).validation.rms_project is None


def test_validate_rms_project_preserves_previous_metadata_and_config(
    fmu_dir: ProjectFMUDirectory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test a failed validation does not overwrite metadata or RMS config."""
    saved_well = RmsWell(name="A-1")
    _set_rms_config(fmu_dir, wells=[saved_well])
    rms_service = Mock()
    rms_service.get_rms_version.return_value = "14.2.2"
    rms_service.get_wells.return_value = [saved_well]
    monkeypatch.setattr(
        "fmu.settings._fmu_dir.getpass.getuser",
        lambda: "test-user",
    )
    service = ProjectValidationService(fmu_dir)
    service.validate_rms_project_and_update_metadata(rms_service, Mock())
    previous_record = fmu_dir.config.load(force=True).validation.rms_project
    saved_rms_before_failure = fmu_dir.config.load().rms
    assert previous_record is not None
    assert saved_rms_before_failure is not None

    rms_service.get_wells.return_value = []
    with pytest.raises(RmsProjectMismatchError):
        service.validate_rms_project_and_update_metadata(rms_service, Mock())

    config_after_failure = fmu_dir.config.load(force=True)
    assert config_after_failure.validation.rms_project == previous_record
    assert config_after_failure.rms == saved_rms_before_failure
