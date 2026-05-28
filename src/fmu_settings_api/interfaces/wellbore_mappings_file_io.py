"""Interface for wellbore mapping import and export files."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING, Self

from fmu.datamodels.context.mappings import (
    DataSystem,
    MappingType,
)
from fmu.settings import (
    InternalRelationType,
    InternalWellboreIdentifierMapping,
    InternalWellboreMappings,
)

if TYPE_CHECKING:
    from fmu.settings import ProjectFMUDirectory


class WellboreMappingsFileIO:
    """Import and export wellbore mappings from project files outside .fmu."""

    def __init__(self: Self, fmu_dir: ProjectFMUDirectory) -> None:
        """Initialize the interface with the project .fmu directory."""
        self._fmu_dir = fmu_dir

    def read_rms_eclipse_csv(
        self: Self, relative_path: str | Path
    ) -> InternalWellboreMappings:
        """Read wellbore mappings from an rms_eclipse.csv-format file.

        Reads a CSV file relative to the project root, converts each RMS_WELL_NAME/
        ECLIPSE_WELL_NAME row into an RMS-to-simulator primary internal wellbore
        mapping, and returns the resulting InternalWellboreMappings object.

        Args:
            relative_path: Path relative to the project root.

        Returns:
            The parsed ``InternalWellboreMappings`` object.

        Raises:
            FileNotFoundError: If the CSV file does not exist.
            ValueError: If the path escapes the project root, required columns are
                missing, or a non-empty row has missing values.
        """
        csv_path = self._fmu_dir.resolve_path_inside_project(Path(relative_path))

        if not csv_path.is_file():
            raise FileNotFoundError(f"CSV file not found: '{csv_path}'")

        with csv_path.open(encoding="utf-8", newline="") as file_handle:
            reader = csv.DictReader(file_handle)
            fieldnames = reader.fieldnames or []
            required_headers = {"RMS_WELL_NAME", "ECLIPSE_WELL_NAME"}
            missing_headers = required_headers.difference(fieldnames)
            if missing_headers:
                missing_headers_text = ", ".join(sorted(missing_headers))
                raise ValueError(
                    f"CSV file is missing required columns: {missing_headers_text}"
                )

            mappings: list[InternalWellboreIdentifierMapping] = []
            primary_source_ids: set[str] = set()
            for row_number, row in enumerate(reader, start=2):
                source_id = (row.get("RMS_WELL_NAME") or "").strip()
                target_id = (row.get("ECLIPSE_WELL_NAME") or "").strip()

                if not source_id and not target_id:
                    continue

                if not source_id or not target_id:
                    raise ValueError(
                        f"CSV row has missing well mapping values at line {row_number}"
                    )

                if source_id not in primary_source_ids:
                    primary_source_ids.add(source_id)
                    mappings.append(
                        InternalWellboreIdentifierMapping(
                            source_system=DataSystem.rms,
                            target_system=DataSystem.rms,
                            mapping_type=MappingType.wellbore,
                            relation_type=InternalRelationType.primary,
                            source_id=source_id,
                            source_uuid=None,
                            target_id=source_id,
                            target_uuid=None,
                        )
                    )

                mappings.append(
                    InternalWellboreIdentifierMapping(
                        source_system=DataSystem.rms,
                        target_system=DataSystem.simulator,
                        mapping_type=MappingType.wellbore,
                        relation_type=InternalRelationType.primary,
                        source_id=source_id,
                        source_uuid=None,
                        target_id=target_id,
                        target_uuid=None,
                    )
                )

        return InternalWellboreMappings(root=mappings)

    def write_rms_simulator_csv(
        self: Self,
        wellbore_mappings: list[InternalWellboreIdentifierMapping],
        relative_path: str | Path,
    ) -> None:
        """Write wellbore mappings to an rms_simulator_mappings.csv-format file.

        Writes a CSV file relative to the project root using two-column format with
        headers rms and simulator.
        If the target CSV file already exists, it is overwritten.

        Args:
            wellbore_mappings: Wellbore mappings to export.
            relative_path: Output path relative to the project root.

        Raises:
            ValueError: If the path escapes the project root or no mappings can be
                represented in the rms_simulator_mappings.csv format.
        """
        csv_path = self._fmu_dir.resolve_path_inside_project(Path(relative_path))
        source_system = DataSystem.rms
        target_system = DataSystem.simulator
        rows = [
            {
                mapping.source_system: mapping.source_id,
                mapping.target_system: mapping.target_id,
            }
            for mapping in wellbore_mappings
        ]

        if not rows:
            raise ValueError(
                "No wellbore mappings available to write to rms_simulator_mappings.csv"
            )

        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", encoding="utf-8", newline="") as file_handle:
            writer = csv.DictWriter(
                file_handle, fieldnames=[source_system, target_system]
            )
            writer.writeheader()
            writer.writerows(rows)

    def write_wellbore_renaming_table(
        self: Self,
        *,
        wellbore_mappings: list[InternalWellboreIdentifierMapping],
        source_system: DataSystem,
        target_system: DataSystem,
        relative_path: str | Path,
    ) -> None:
        """Write wellbore mappings to a renaming table file.

        Writes a renaming table file relative to the project root,
        with the header row ``SETNAMES``, the source system, and the target
        system separated by tab characters, followed by one source and one
        target identifier per line.
        If the target renaming_table file already exists, it is overwritten.

        Args:
            wellbore_mappings: Wellbore mappings to export.
            source_system: Source system to use for the first output column.
            target_system: Target system to use for the second output column.
            relative_path: Output path relative to the project root.

        Raises:
            ValueError: If the path escapes the project root, no mappings can be
                represented in the renaming table format.
        """
        renaming_table_path = self._fmu_dir.resolve_path_inside_project(
            Path(relative_path)
        )
        if not wellbore_mappings:
            raise ValueError(
                f"No wellbore mappings available to write to {renaming_table_path.name}"
            )

        renaming_table_path.parent.mkdir(parents=True, exist_ok=True)
        header = f"SETNAMES {source_system.value}\t{target_system.value}"

        with renaming_table_path.open("w", encoding="utf-8", newline="") as file_handle:
            file_handle.write(f"{header}\n")
            for mapping in wellbore_mappings:
                file_handle.write(f"{mapping.source_id}\t{mapping.target_id}\n")
