"""Interface for wellbore mapping import and export files."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING, Final, Self

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

    WELL_INFO_DIRECTORY: Final[Path] = Path("rms/input/well_modelling/well_info")
    RMS_ECLIPSE_CSV_PATH: Final[Path] = WELL_INFO_DIRECTORY / "rms_eclipse.csv"
    RMS_SIMULATOR_CSV_PATH: Final[Path] = WELL_INFO_DIRECTORY / "rms_simulator.csv"
    RMS_SIMULATOR_RENAMING_TABLE_PATH: Final[Path] = (
        WELL_INFO_DIRECTORY / "rms_simulator.renaming_table"
    )
    RMS_PDM_RENAMING_TABLE_PATH: Final[Path] = (
        WELL_INFO_DIRECTORY / "rms_pdm.renaming_table"
    )

    def __init__(self: Self, fmu_dir: ProjectFMUDirectory) -> None:
        """Initialize the interface with the project .fmu directory."""
        self._fmu_dir = fmu_dir

    def read_rms_eclipse_csv(
        self: Self, relative_path: str | Path | None = None
    ) -> InternalWellboreMappings:
        """Read wellbore mappings from an rms_eclipse.csv-format file.

        Reads a CSV file relative to the project root, defaults to
        rms/input/well_modelling/well_info/rms_eclipse.csv, converts each
        RMS_WELL_NAME/ECLIPSE_WELL_NAME row into an RMS-to-simulator primary
        internal wellbore mapping, and returns the resulting InternalWellboreMappings
        object.

        Args:
            relative_path: Optional path relative to the project root.
                Defaults to rms/input/well_modelling/well_info/rms_eclipse.csv.

        Returns:
            The parsed ``InternalWellboreMappings`` object.

        Raises:
            FileNotFoundError: If the CSV file does not exist.
            ValueError: If the path escapes the project root, required columns are
                missing, or a non-empty row has missing values.
        """
        csv_path = self._resolve_path(relative_path, self.RMS_ECLIPSE_CSV_PATH)

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
        relative_path: str | Path | None = None,
    ) -> None:
        """Write wellbore mappings to an rms_simulator.csv-format file.

        Writes a CSV file relative to the project root, defaults to
        rms/input/well_modelling/well_info/rms_simulator.csv, using two-column
        format with headers RMS_WELL_NAME and SIMULATOR_WELL_NAME.
        If the target CSV file already exists, it is overwritten.

        Args:
            wellbore_mappings: Wellbore mappings to export.
            relative_path: Optional output path relative to the project root.
                Defaults to rms/input/well_modelling/well_info/rms_simulator.csv.

        Raises:
            ValueError: If the path escapes the project root or no mappings can be
                represented in the rms_simulator.csv format.
        """
        csv_path = self._resolve_path(relative_path, self.RMS_SIMULATOR_CSV_PATH)
        rows = [
            {
                "RMS_WELL_NAME": mapping.source_id,
                "SIMULATOR_WELL_NAME": mapping.target_id,
            }
            for mapping in wellbore_mappings
        ]

        if not rows:
            raise ValueError(
                "No wellbore mappings available to write to rms_simulator.csv"
            )

        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", encoding="utf-8", newline="") as file_handle:
            writer = csv.DictWriter(
                file_handle, fieldnames=["RMS_WELL_NAME", "SIMULATOR_WELL_NAME"]
            )
            writer.writeheader()
            writer.writerows(rows)

    def write_rms_simulator_renaming_table(
        self: Self,
        wellbore_mappings: list[InternalWellboreIdentifierMapping],
        relative_path: str | Path | None = None,
    ) -> None:
        """Write wellbore mappings to an rms_simulator.renaming_table file.

        Writes a renaming table file relative to the project root,
        defaults to rms/input/well_modelling/well_info/rms_simulator.renaming_table,
        with the header row ``SETNAMES``, ``rms``, and ``simulator`` separated by
        tab characters, followed by one source and one target identifier per line.
        If the target renaming_table file already exists, it is overwritten.

        Args:
            wellbore_mappings: Wellbore mappings to export.
            relative_path: Optional output path relative to the project root.
                Defaults to
                rms/input/well_modelling/well_info/rms_simulator.renaming_table.

        Raises:
            ValueError: If the path escapes the project root or no mappings can be
                represented in the rms_simulator.renaming_table format.
        """
        renaming_table_path = self._resolve_path(
            relative_path, self.RMS_SIMULATOR_RENAMING_TABLE_PATH
        )
        if not wellbore_mappings:
            raise ValueError(
                "No wellbore mappings available to write to "
                "rms_simulator.renaming_table"
            )

        self._write_wellbore_renaming_table(
            wellbore_mappings,
            renaming_table_path=renaming_table_path,
            source_system=DataSystem.rms,
            target_system=DataSystem.simulator,
        )

    def write_rms_pdm_renaming_table(
        self: Self,
        wellbore_mappings: list[InternalWellboreIdentifierMapping],
        relative_path: str | Path | None = None,
    ) -> None:
        """Write wellbore mappings to a rms_pdm.renaming_table file.

        Writes a renaming table file relative to the project root,
        defaults to rms/input/well_modelling/well_info/rms_pdm.renaming_table,
        with the header row ``SETNAMES``, ``rms``, and ``pdm`` separated by
        tab characters, followed by one source and one target identifier per line.
        If the target renaming_table file already exists, it is overwritten.

        Args:
            wellbore_mappings: Wellbore mappings to export.
            relative_path: Optional output path relative to the project root.
                Defaults to
                rms/input/well_modelling/well_info/rms_pdm.renaming_table.

        Raises:
            ValueError: If the path escapes the project root or no mappings can be
                represented in the rms_pdm.renaming_table format.
        """
        renaming_table_path = self._resolve_path(
            relative_path, self.RMS_PDM_RENAMING_TABLE_PATH
        )
        if not wellbore_mappings:
            raise ValueError(
                "No wellbore mappings available to write to rms_pdm.renaming_table"
            )

        self._write_wellbore_renaming_table(
            wellbore_mappings,
            renaming_table_path=renaming_table_path,
            source_system=DataSystem.rms,
            target_system=DataSystem.pdm,
        )

    def _resolve_path(
        self: Self, relative_path: str | Path | None, default_path: Path
    ) -> Path:
        """Resolve an optional project-relative path inside the project root."""
        return self._fmu_dir.resolve_path_inside_project(
            Path(relative_path or default_path)
        )

    def _write_wellbore_renaming_table(
        self: Self,
        wellbore_mappings: list[InternalWellboreIdentifierMapping],
        *,
        renaming_table_path: Path,
        source_system: DataSystem,
        target_system: DataSystem,
    ) -> None:
        """Write wellbore mappings to a tab-separated renaming table."""
        renaming_table_path.parent.mkdir(parents=True, exist_ok=True)
        header = f"SETNAMES {source_system.value}\t{target_system.value}"

        with renaming_table_path.open("w", encoding="utf-8", newline="") as file_handle:
            file_handle.write(f"{header}\n")
            for mapping in wellbore_mappings:
                file_handle.write(f"{mapping.source_id}\t{mapping.target_id}\n")
