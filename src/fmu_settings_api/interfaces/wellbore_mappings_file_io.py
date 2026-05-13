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
    RMS_ECLIPSE_RENAMING_TABLE_PATH: Final[Path] = (
        WELL_INFO_DIRECTORY / "rms_eclipse.renaming_table"
    )
    PDM_RMS_RENAMING_TABLE_PATH: Final[Path] = (
        WELL_INFO_DIRECTORY / "pdm_rms.renaming_table"
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
        csv_path, _ = self._resolve_path(relative_path, self.RMS_ECLIPSE_CSV_PATH)

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

    def write_rms_eclipse_csv(
        self: Self,
        wellbore_mappings: InternalWellboreMappings,
        relative_path: str | Path | None = None,
    ) -> Path:
        """Write wellbore mappings to an rms_eclipse.csv-format file.

        Writes a CSV file relative to the project root, defaults to
        rms/input/well_modelling/well_info/rms_eclipse.csv, using the rms_eclipse.csv
        two-column format with headers RMS_WELL_NAME and ECLIPSE_WELL_NAME.
        If the target CSV file already exists, it is overwritten.

        Only RMS-to-simulator primary wellbore mappings are exported. Other
        mapping systems, mapping types, and relation types are ignored.

        Args:
            wellbore_mappings: ``InternalWellboreMappings`` object to export.
            relative_path: Optional output path relative to the project root.
                Defaults to rms/input/well_modelling/well_info/rms_eclipse.csv.

        Returns:
            The path to the written CSV file, relative to the project root.

        Raises:
            ValueError: If the path escapes the project root or no mappings can be
                represented in the rms_eclipse.csv format.
        """
        csv_path, resolved_relative_path = self._resolve_path(
            relative_path, self.RMS_ECLIPSE_CSV_PATH
        )
        rows = [
            {
                "RMS_WELL_NAME": mapping.source_id,
                "ECLIPSE_WELL_NAME": mapping.target_id,
            }
            for mapping in self._filter_wellbore_mappings(
                wellbore_mappings,
                source_system=DataSystem.rms,
                target_system=DataSystem.simulator,
                relation_type=InternalRelationType.primary,
            )
        ]

        if not rows:
            raise ValueError(
                "No RMS-to-simulator primary wellbore mappings available to "
                "write to rms_eclipse.csv"
            )

        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", encoding="utf-8", newline="") as file_handle:
            writer = csv.DictWriter(
                file_handle, fieldnames=["RMS_WELL_NAME", "ECLIPSE_WELL_NAME"]
            )
            writer.writeheader()
            writer.writerows(rows)

        return resolved_relative_path

    def write_rms_eclipse_renaming_table(
        self: Self,
        wellbore_mappings: InternalWellboreMappings,
        relative_path: str | Path | None = None,
    ) -> Path:
        """Write wellbore mappings to an rms_eclipse.renaming_table file.

        Writes a renaming table file relative to the project root,
        defaults to rms/input/well_modelling/well_info/rms_eclipse.renaming_table,
        with the header row ``SETNAMES``, ``rms``, and ``eclipse`` separated by
        tab characters, followed by one source and one target identifier per line.
        If the target renaming_table file already exists, it is overwritten.

        Only RMS-to-simulator primary wellbore mappings are exported. Other
        mapping systems, mapping types, and relation types are ignored.

        Args:
            wellbore_mappings: ``InternalWellboreMappings`` object to export.
            relative_path: Optional output path relative to the project root.
                Defaults to
                rms/input/well_modelling/well_info/rms_eclipse.renaming_table.

        Returns:
            The path to the written renaming table, relative to the project root.

        Raises:
            ValueError: If the path escapes the project root or no mappings can be
                represented in the rms_eclipse.renaming_table format.
        """
        renaming_table_path, resolved_relative_path = self._resolve_path(
            relative_path, self.RMS_ECLIPSE_RENAMING_TABLE_PATH
        )
        filtered_wellbore_mappings = self._filter_wellbore_mappings(
            wellbore_mappings,
            source_system=DataSystem.rms,
            target_system=DataSystem.simulator,
            relation_type=InternalRelationType.primary,
        )

        if not filtered_wellbore_mappings:
            raise ValueError(
                "No RMS-to-simulator primary wellbore mappings available to "
                "write to rms_eclipse.renaming_table"
            )

        self._write_wellbore_renaming_table(
            filtered_wellbore_mappings,
            renaming_table_path=renaming_table_path,
            header="SETNAMES rms\teclipse",
        )

        return resolved_relative_path

    def write_pdm_rms_renaming_table(
        self: Self,
        wellbore_mappings: InternalWellboreMappings,
        relative_path: str | Path | None = None,
    ) -> Path:
        """Write wellbore mappings to a pdm_rms.renaming_table file.

        Writes a renaming table file relative to the project root,
        defaults to rms/input/well_modelling/well_info/pdm_rms.renaming_table,
        with the header row ``SETNAMES``, ``pdm``, and ``rms`` separated by
        tab characters, followed by one source and one target identifier per line.
        If the target renaming_table file already exists, it is overwritten.

        Only PDM-to-RMS primary wellbore mappings are exported. Other mapping
        systems, mapping types, and relation types are ignored.

        Args:
            wellbore_mappings: ``InternalWellboreMappings`` object to export.
            relative_path: Optional output path relative to the project root.
                Defaults to
                rms/input/well_modelling/well_info/pdm_rms.renaming_table.

        Returns:
            The path to the written renaming table, relative to the project root.

        Raises:
            ValueError: If the path escapes the project root or no mappings can be
                represented in the pdm_rms.renaming_table format.
        """
        renaming_table_path, resolved_relative_path = self._resolve_path(
            relative_path, self.PDM_RMS_RENAMING_TABLE_PATH
        )
        filtered_wellbore_mappings = self._filter_wellbore_mappings(
            wellbore_mappings,
            source_system=DataSystem.pdm,
            target_system=DataSystem.rms,
            relation_type=InternalRelationType.primary,
        )

        if not filtered_wellbore_mappings:
            raise ValueError(
                "No PDM-to-RMS primary wellbore mappings available to "
                "write to pdm_rms.renaming_table"
            )

        self._write_wellbore_renaming_table(
            filtered_wellbore_mappings,
            renaming_table_path=renaming_table_path,
            header="SETNAMES pdm\trms",
        )
        return resolved_relative_path

    def _resolve_path(
        self: Self, relative_path: str | Path | None, default_path: Path
    ) -> tuple[Path, Path]:
        """Resolve an optional project-relative path and return both path forms."""
        resolved_path = self._fmu_dir.resolve_path_inside_project(
            Path(relative_path or default_path)
        )

        return resolved_path, resolved_path.relative_to(self._fmu_dir.base_path)

    def _write_wellbore_renaming_table(
        self: Self,
        wellbore_mappings: list[InternalWellboreIdentifierMapping],
        *,
        renaming_table_path: Path,
        header: str,
    ) -> None:
        """Write wellbore mappings to a tab-separated renaming table."""
        renaming_table_path.parent.mkdir(parents=True, exist_ok=True)

        with renaming_table_path.open("w", encoding="utf-8", newline="") as file_handle:
            file_handle.write(f"{header}\n")
            for mapping in wellbore_mappings:
                file_handle.write(f"{mapping.source_id}\t{mapping.target_id}\n")

    def _filter_wellbore_mappings(
        self: Self,
        wellbore_mappings: InternalWellboreMappings,
        *,
        source_system: DataSystem,
        target_system: DataSystem,
        relation_type: InternalRelationType,
    ) -> list[InternalWellboreIdentifierMapping]:
        """Return wellbore mappings matching source, target, and relation."""
        return [
            mapping
            for mapping in wellbore_mappings
            if (
                mapping.source_system == source_system
                and mapping.target_system == target_system
                and mapping.mapping_type == MappingType.wellbore
                and mapping.relation_type == relation_type
                and mapping.target_id is not None
            )
        ]
