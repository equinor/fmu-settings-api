"""Service for validating project configuration against external sources."""

import asyncio
import json
from collections.abc import Sequence

from fmu.datamodels.common import Smda
from fmu.settings import ProjectFMUDirectory
from fmu.settings.models.project_config import (
    RmsHorizon,
    RmsStratigraphicZone,
    RmsWell,
)
from pydantic import BaseModel
from runrms.api import RmsApiProxy

from fmu_settings_api.models.project import ValidationMismatch
from fmu_settings_api.models.smda import SmdaMasterdataResult, SmdaSelectedField
from fmu_settings_api.services.rms import RmsService
from fmu_settings_api.services.smda import SmdaService


class MasterdataSmdaMismatchError(ValueError):
    """Raised when project masterdata does not match SMDA."""

    def __init__(self, mismatches: list[ValidationMismatch]) -> None:
        """Initialize with validation mismatches."""
        self.mismatches = mismatches


class RmsProjectMismatchError(ValueError):
    """Raised when saved RMS settings do not match the open RMS project."""

    def __init__(self, mismatches: list[ValidationMismatch]) -> None:
        """Initialize with validation mismatches."""
        self.mismatches = mismatches


class ProjectValidationService:
    """Service for validating project configuration."""

    def __init__(self, fmu_dir: ProjectFMUDirectory) -> None:
        """Initialize the service with project access."""
        self._fmu_dir = fmu_dir

    async def validate_masterdata_against_smda_and_update_metadata(
        self,
        smda_service: SmdaService,
    ) -> None:
        """Validate saved SMDA masterdata and update validation metadata on success.

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
                smda_service.get_masterdata([selected_field])
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
            # SmdaMasterdataResult uses plural form for some of the attribute
            # names compared to the Smda class used to save the SMDA data in
            # .fmu. Therefore, we need to add an "s" when comparing some of
            # the fields, e.g. coordinate_system must be compared against
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

        self._fmu_dir.update_validation_metadata("masterdata_smda")

    def validate_rms_project_and_update_metadata(
        self,
        rms_service: RmsService,
        opened_rms_project: RmsApiProxy,
    ) -> None:
        """Validate saved RMS settings and update validation metadata on success.

        The check compares the saved RMS version, horizons, zones, and wells
        with the open project. For wells, it checks every value except
        ``planned``.

        Every saved horizon, zone, and well must exist in the open project. The
        order of these items does not matter.

        An empty saved list is valid. It means the user saved no horizons, zones,
        or wells, either by clearing the category or because the open RMS project
        had none to save.

        The coordinate system is not checked because it is not currently saved
        in the project configuration.
        """
        config = self._fmu_dir.config.load()
        if config.rms is None:
            raise ValueError("No RMS settings are saved in the FMU project.")

        saved_rms = config.rms
        mismatches: list[ValidationMismatch] = []

        current_version = rms_service.get_rms_version(saved_rms.path)
        if saved_rms.version != current_version:
            mismatches.append(
                ValidationMismatch(
                    key="rms.version",
                    saved_value=saved_rms.version,
                    source_value=current_version,
                    message=(
                        "The RMS version saved in the FMU project does not match "
                        "the version of the open RMS project."
                    ),
                )
            )

        if saved_rms.horizons is not None:
            mismatches.extend(
                _find_rms_item_mismatches(
                    key_prefix="rms.horizons",
                    item_label="horizon",
                    saved_items=saved_rms.horizons,
                    source_items=rms_service.get_horizons(opened_rms_project),
                )
            )

        if saved_rms.zones is not None:
            mismatches.extend(
                _find_rms_item_mismatches(
                    key_prefix="rms.zones",
                    item_label="zone",
                    saved_items=saved_rms.zones,
                    source_items=rms_service.get_zones(opened_rms_project),
                )
            )

        if saved_rms.wells is not None:
            mismatches.extend(
                _find_rms_item_mismatches(
                    key_prefix="rms.wells",
                    item_label="well",
                    saved_items=saved_rms.wells,
                    source_items=rms_service.get_wells(opened_rms_project),
                    ignored_fields={"planned"},
                )
            )

        if mismatches:
            raise RmsProjectMismatchError(mismatches)

        self._fmu_dir.update_validation_metadata("rms_project")


def _find_rms_item_mismatches(
    *,
    key_prefix: str,
    item_label: str,
    saved_items: Sequence[RmsHorizon | RmsStratigraphicZone | RmsWell],
    source_items: Sequence[RmsHorizon | RmsStratigraphicZone | RmsWell],
    ignored_fields: set[str] | None = None,
) -> list[ValidationMismatch]:
    """Find saved RMS items missing from or different in the open RMS project.

    Item order is ignored. Fields in ``ignored_fields`` are excluded from the
    comparison.
    """
    source_by_name = {item.name: item for item in source_items}
    mismatches: list[ValidationMismatch] = []

    for saved_item in saved_items:
        source_item = source_by_name.get(saved_item.name)
        saved_value = saved_item.model_dump(mode="json")

        if source_item is None:
            mismatches.append(
                ValidationMismatch(
                    key=f"{key_prefix}.{saved_item.name}",
                    saved_value=saved_value,
                    source_value=None,
                    message=(
                        f"RMS {item_label} '{saved_item.name}' is saved in the FMU "
                        "project but is not present in the open RMS project."
                    ),
                )
            )
            continue

        if saved_item.model_dump(
            mode="json", exclude=ignored_fields
        ) != source_item.model_dump(mode="json", exclude=ignored_fields):
            mismatches.append(
                ValidationMismatch(
                    key=f"{key_prefix}.{saved_item.name}",
                    saved_value=saved_value,
                    source_value=source_item.model_dump(mode="json"),
                    message=(
                        f"RMS {item_label} '{saved_item.name}' has different "
                        "settings in the FMU project and the open RMS project."
                    ),
                )
            )

    return mismatches
