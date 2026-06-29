"""Tests for ProjectValidationService."""

from typing import Any
from unittest.mock import AsyncMock, Mock, call
from uuid import UUID

import pytest
from fmu.datamodels.common import Smda
from fmu.settings import ProjectFMUDirectory

from fmu_settings_api.models.smda import SmdaMasterdataResult, SmdaSelectedField
from fmu_settings_api.services.project_validation import (
    MasterdataSmdaMismatchError,
    ProjectValidationService,
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
        "fmu_settings_api.services.project_validation.getpass.getuser",
        lambda: "test-user",
    )

    await ProjectValidationService(fmu_dir, smda_service).validate_masterdata_smda()

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

    await ProjectValidationService(fmu_dir, smda_service).validate_masterdata_smda()

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

    await ProjectValidationService(fmu_dir, smda_service).validate_masterdata_smda()

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
        await ProjectValidationService(fmu_dir, smda_service).validate_masterdata_smda()

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
        await ProjectValidationService(fmu_dir, smda_service).validate_masterdata_smda()
