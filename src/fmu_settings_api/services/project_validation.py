"""Service for validating project configuration against external sources."""

import asyncio
import getpass
import json
from datetime import UTC, datetime

from fmu.datamodels.common import Smda
from fmu.settings import ProjectFMUDirectory
from fmu.settings.models.project_config import ValidationRecord
from pydantic import BaseModel

from fmu_settings_api.models.project import ValidationMismatch
from fmu_settings_api.models.smda import SmdaMasterdataResult, SmdaSelectedField
from fmu_settings_api.services.smda import SmdaService


class MasterdataSmdaMismatchError(ValueError):
    """Raised when project masterdata does not match SMDA."""

    def __init__(self, mismatches: list[ValidationMismatch]) -> None:
        """Initialize with validation mismatches."""
        self.mismatches = mismatches


class ProjectValidationService:
    """Service for validating project configuration."""

    def __init__(self, fmu_dir: ProjectFMUDirectory, smda_service: SmdaService) -> None:
        """Initialize the service with project and SMDA access."""
        self._fmu_dir = fmu_dir
        self._smda_service = smda_service

    async def validate_masterdata_smda(self) -> None:
        """Validate saved SMDA masterdata and update validation metadata.

        Flow:
            1. Load the saved project SMDA config.
            2. Query current SMDA masterdata once per saved field, since SMDA
               masterdata lookup intentionally handles one UUID-backed field at a
               time.
            3. Combine the per-field SMDA responses into one validation source.
            4. Compare each saved SMDA section with the current SMDA values.
            5. Raise mismatch details if any saved value is missing from SMDA.
            6. Store validation metadata when all saved values are still present.
        """
        config = self._fmu_dir.config.load()
        if config.masterdata is None:
            raise ValueError(
                "Project masterdata must be set before validating against SMDA."
            )

        saved_smda = config.masterdata.smda
        selected_fields = [
            SmdaSelectedField(identifier=field.identifier, uuid=field.uuid)
            for field in saved_smda.field
        ]
        per_field_smda_results = await asyncio.gather(
            *[
                self._smda_service.get_masterdata([selected_field])
                for selected_field in selected_fields
            ]
        )
        combined_smda_result = SmdaMasterdataResult(
            field=[
                field for result in per_field_smda_results for field in result.field
            ],
            country=[
                country
                for result in per_field_smda_results
                for country in result.country
            ],
            discovery=[
                discovery
                for result in per_field_smda_results
                for discovery in result.discovery
            ],
            stratigraphic_columns=[
                stratigraphic_column
                for result in per_field_smda_results
                for stratigraphic_column in result.stratigraphic_columns
            ],
            field_coordinate_system=per_field_smda_results[0].field_coordinate_system,
            coordinate_systems=[
                coordinate_system
                for result in per_field_smda_results
                for coordinate_system in result.coordinate_systems
            ],
        )

        mismatches: list[ValidationMismatch] = []
        for smda_attr in Smda.model_fields:
            # SmdaMasterdataResult uses plural list fields for some saved
            # config values, e.g. coordinate_system must be compared against
            # coordinate_systems, and stratigraphic_column against
            # stratigraphic_columns.
            smda_result_attr = (
                smda_attr
                if hasattr(combined_smda_result, smda_attr)
                else f"{smda_attr}s"
            )
            saved_value = getattr(saved_smda, smda_attr)
            source_value = getattr(combined_smda_result, smda_result_attr)
            saved_values = (
                [saved_value] if isinstance(saved_value, BaseModel) else saved_value
            )
            saved_keys = {
                json.dumps(item.model_dump(mode="json"), sort_keys=True)
                for item in saved_values
            }
            source_keys = {
                json.dumps(item.model_dump(mode="json"), sort_keys=True)
                for item in source_value
            }
            if saved_keys <= source_keys:
                continue

            mismatches.append(
                ValidationMismatch(
                    key=f"masterdata.smda.{smda_attr}",
                    saved_value=(
                        saved_value.model_dump(mode="json")
                        if isinstance(saved_value, BaseModel)
                        else [item.model_dump(mode="json") for item in saved_value]
                    ),
                    source_value=[
                        item.model_dump(mode="json") for item in source_value
                    ],
                    message=(
                        f"Project config masterdata '{smda_attr}' "
                        "is not present in current SMDA data"
                    ),
                )
            )

        if mismatches:
            raise MasterdataSmdaMismatchError(mismatches)

        record = ValidationRecord(
            last_validated_at=datetime.now(UTC),
            last_validated_by=getpass.getuser(),
        )
        self._fmu_dir.set_config_value(
            "validation.masterdata_smda", record.model_dump()
        )
