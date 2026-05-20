"""Tests for the wellbore mapping file interface."""

from collections.abc import Callable
from pathlib import Path

import pytest
from fmu.datamodels.context.mappings import DataSystem
from fmu.settings import (
    InternalWellboreIdentifierMapping,
    InternalWellboreMappings,
    ProjectFMUDirectory,
)

from fmu_settings_api.interfaces.wellbore_mappings_file_io import (
    WellboreMappingsFileIO,
)


def test_read_rms_eclipse_csv_default_path(
    fmu_dir: ProjectFMUDirectory,
    make_rms_simulator_mappings: Callable[[], InternalWellboreMappings],
) -> None:
    """Default CSV path is converted to internal wellbore mappings."""
    file_io = WellboreMappingsFileIO(fmu_dir)
    csv_path = fmu_dir.base_path / "rms/input/well_modelling/well_info/rms_eclipse.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(
        "RMS_WELL_NAME,ECLIPSE_WELL_NAME\n30_9-B-43_A,B43A\n",
        encoding="utf-8",
    )

    well_mappings = file_io.read_rms_eclipse_csv()

    assert well_mappings == make_rms_simulator_mappings()


def test_read_rms_eclipse_csv_custom_path(
    fmu_dir: ProjectFMUDirectory,
    make_rms_simulator_mappings: Callable[[], InternalWellboreMappings],
) -> None:
    """Custom CSV path is converted to internal wellbore mappings."""
    file_io = WellboreMappingsFileIO(fmu_dir)
    csv_relative_path = Path("data/custom/rms_eclipse.csv")
    csv_path = fmu_dir.base_path / csv_relative_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(
        "RMS_WELL_NAME,ECLIPSE_WELL_NAME\n30_9-B-43_A,B43A\n",
        encoding="utf-8",
    )

    assert (
        file_io.read_rms_eclipse_csv(csv_relative_path) == make_rms_simulator_mappings()
    )


def test_read_rms_eclipse_csv_raises_for_missing_file(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Missing CSV files should raise FileNotFoundError."""
    file_io = WellboreMappingsFileIO(fmu_dir)
    csv_relative_path = Path("data/custom/missing.csv")

    with pytest.raises(FileNotFoundError, match="CSV file not found"):
        file_io.read_rms_eclipse_csv(csv_relative_path)


def test_read_rms_eclipse_csv_raises_for_missing_headers(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Missing required CSV headers should raise a ValueError."""
    file_io = WellboreMappingsFileIO(fmu_dir)
    csv_relative_path = Path("data/custom/invalid_headers.csv")
    csv_path = fmu_dir.base_path / csv_relative_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(
        "RMS_WELL_NAME,WRONG_HEADER\n30_9-B-43_A,B43A\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError, match="CSV file is missing required columns: ECLIPSE_WELL_NAME"
    ):
        file_io.read_rms_eclipse_csv(csv_relative_path)


def test_read_rms_eclipse_csv_raises_for_partial_row(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Partially filled CSV rows should raise a ValueError."""
    file_io = WellboreMappingsFileIO(fmu_dir)
    csv_relative_path = Path("data/custom/partial_row.csv")
    csv_path = fmu_dir.base_path / csv_relative_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(
        "RMS_WELL_NAME,ECLIPSE_WELL_NAME\n30_9-B-43_A,\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing well mapping values at line 2"):
        file_io.read_rms_eclipse_csv(csv_relative_path)


def test_read_rms_eclipse_csv_skips_empty_rows(
    fmu_dir: ProjectFMUDirectory,
    make_rms_simulator_mappings: Callable[[], InternalWellboreMappings],
) -> None:
    """Empty CSV rows should be ignored."""
    file_io = WellboreMappingsFileIO(fmu_dir)
    csv_relative_path = Path("data/custom/empty_rows.csv")
    csv_path = fmu_dir.base_path / csv_relative_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(
        "RMS_WELL_NAME,ECLIPSE_WELL_NAME\n30_9-B-43_A,B43A\n,\n",
        encoding="utf-8",
    )

    assert (
        file_io.read_rms_eclipse_csv(csv_relative_path) == make_rms_simulator_mappings()
    )


@pytest.mark.parametrize("relative_path", [Path("../outside.csv"), Path("/tmp/x.csv")])
def test_read_rms_eclipse_csv_rejects_paths_outside_project_root(
    fmu_dir: ProjectFMUDirectory,
    relative_path: Path,
) -> None:
    """CSV reads must reject paths outside the project root."""
    file_io = WellboreMappingsFileIO(fmu_dir)

    with pytest.raises(ValueError, match="must stay within the project root"):
        file_io.read_rms_eclipse_csv(relative_path)


def test_write_rms_simulator_csv_writes_expected_format(
    fmu_dir: ProjectFMUDirectory,
    make_wellbore_mapping: Callable[..., InternalWellboreIdentifierMapping],
) -> None:
    """Well mappings are written using the rms_simulator.csv format."""
    file_io = WellboreMappingsFileIO(fmu_dir)
    csv_relative_path = Path("data/custom/rms_simulator.csv")

    file_io.write_rms_simulator_csv(
        [make_wellbore_mapping()],
        relative_path=csv_relative_path,
    )

    assert (fmu_dir.base_path / csv_relative_path).read_text(encoding="utf-8") == (
        "RMS_WELL_NAME,SIMULATOR_WELL_NAME\n30_9-B-43_A,B43A\n"
    )


def test_write_rms_simulator_csv_uses_default_path(
    fmu_dir: ProjectFMUDirectory,
    make_wellbore_mapping: Callable[..., InternalWellboreIdentifierMapping],
) -> None:
    """CSV export should use the default project-relative path when omitted."""
    file_io = WellboreMappingsFileIO(fmu_dir)

    file_io.write_rms_simulator_csv([make_wellbore_mapping()])

    assert (
        fmu_dir.base_path / WellboreMappingsFileIO.RMS_SIMULATOR_CSV_PATH
    ).read_text(encoding="utf-8") == (
        "RMS_WELL_NAME,SIMULATOR_WELL_NAME\n30_9-B-43_A,B43A\n"
    )


def test_write_rms_simulator_renaming_table_writes_expected_format(
    fmu_dir: ProjectFMUDirectory,
    make_wellbore_mapping: Callable[..., InternalWellboreIdentifierMapping],
) -> None:
    """Well mappings are written using the renaming-table format."""
    file_io = WellboreMappingsFileIO(fmu_dir)
    relative_path = Path("data/custom/rms_simulator.renaming_table")

    file_io.write_rms_simulator_renaming_table(
        [make_wellbore_mapping()],
        relative_path=relative_path,
    )

    assert (fmu_dir.base_path / relative_path).read_text(encoding="utf-8") == (
        "SETNAMES rms\tsimulator\n30_9-B-43_A\tB43A\n"
    )


def test_write_rms_simulator_renaming_table_uses_default_path(
    fmu_dir: ProjectFMUDirectory,
    make_wellbore_mapping: Callable[..., InternalWellboreIdentifierMapping],
) -> None:
    """RMS renaming-table export should use the default project-relative path."""
    file_io = WellboreMappingsFileIO(fmu_dir)

    file_io.write_rms_simulator_renaming_table([make_wellbore_mapping()])

    assert (
        fmu_dir.base_path / WellboreMappingsFileIO.RMS_SIMULATOR_RENAMING_TABLE_PATH
    ).read_text(encoding="utf-8") == ("SETNAMES rms\tsimulator\n30_9-B-43_A\tB43A\n")


def test_write_rms_simulator_renaming_table_raises_when_no_rows_match(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """RMS renaming-table export raises when no mappings match the format."""
    file_io = WellboreMappingsFileIO(fmu_dir)

    with pytest.raises(
        ValueError,
        match="No wellbore mappings available to write to rms_simulator.renaming_table",
    ):
        file_io.write_rms_simulator_renaming_table([])


def test_write_rms_pdm_renaming_table_writes_expected_format(
    fmu_dir: ProjectFMUDirectory,
    make_wellbore_mapping: Callable[..., InternalWellboreIdentifierMapping],
) -> None:
    """RMS-to-PDM mappings are written using the renaming-table format."""
    file_io = WellboreMappingsFileIO(fmu_dir)
    relative_path = Path("data/custom/rms_pdm.renaming_table")

    file_io.write_rms_pdm_renaming_table(
        [
            make_wellbore_mapping(
                source_system=DataSystem.rms,
                target_system=DataSystem.pdm,
                source_id="30_9-B-43_A",
                target_id="30/9-B-43 A",
            ),
        ],
        relative_path=relative_path,
    )

    assert (fmu_dir.base_path / relative_path).read_text(encoding="utf-8") == (
        "SETNAMES rms\tpdm\n30_9-B-43_A\t30/9-B-43 A\n"
    )


def test_write_rms_pdm_renaming_table_uses_default_path(
    fmu_dir: ProjectFMUDirectory,
    make_wellbore_mapping: Callable[..., InternalWellboreIdentifierMapping],
) -> None:
    """RMS-to-PDM renaming-table export should use the default path."""
    file_io = WellboreMappingsFileIO(fmu_dir)

    file_io.write_rms_pdm_renaming_table(
        [
            make_wellbore_mapping(
                source_system=DataSystem.rms,
                target_system=DataSystem.pdm,
                source_id="30_9-B-43_A",
                target_id="30/9-B-43 A",
            ),
        ]
    )

    assert (
        fmu_dir.base_path / WellboreMappingsFileIO.RMS_PDM_RENAMING_TABLE_PATH
    ).read_text(encoding="utf-8") == ("SETNAMES rms\tpdm\n30_9-B-43_A\t30/9-B-43 A\n")


def test_write_rms_simulator_csv_raises_when_no_rows_match(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """CSV export raises when no mappings can be represented in the file format."""
    file_io = WellboreMappingsFileIO(fmu_dir)
    with pytest.raises(
        ValueError,
        match="No wellbore mappings available to write to rms_simulator.csv",
    ):
        file_io.write_rms_simulator_csv([])


def test_write_rms_simulator_csv_raises_and_preserves_file_when_no_rows_match(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Failed CSV export should not overwrite an existing file."""
    file_io = WellboreMappingsFileIO(fmu_dir)
    csv_relative_path = Path("data/custom/existing_rms_simulator.csv")
    csv_path = fmu_dir.base_path / csv_relative_path
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text("existing-content\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="No wellbore mappings available to write to rms_simulator.csv",
    ):
        file_io.write_rms_simulator_csv(
            [],
            relative_path=csv_relative_path,
        )

    assert csv_path.read_text(encoding="utf-8") == "existing-content\n"


def test_write_rms_pdm_renaming_table_raises_and_preserves_file_when_no_rows_match(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Failed RMS-to-PDM renaming-table export should not overwrite a file."""
    file_io = WellboreMappingsFileIO(fmu_dir)
    relative_path = Path("data/custom/existing_rms_pdm.renaming_table")
    renaming_table_path = fmu_dir.base_path / relative_path
    renaming_table_path.parent.mkdir(parents=True, exist_ok=True)
    renaming_table_path.write_text("existing-content\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="No wellbore mappings available to write to rms_pdm.renaming_table",
    ):
        file_io.write_rms_pdm_renaming_table(
            [],
            relative_path=relative_path,
        )

    assert renaming_table_path.read_text(encoding="utf-8") == "existing-content\n"


@pytest.mark.parametrize("relative_path", [Path("../outside.csv"), Path("/tmp/x.csv")])
def test_paths_must_stay_inside_project_root(
    fmu_dir: ProjectFMUDirectory,
    relative_path: Path,
    make_wellbore_mapping: Callable[..., InternalWellboreIdentifierMapping],
) -> None:
    """File operations must reject paths outside the project root."""
    file_io = WellboreMappingsFileIO(fmu_dir)
    with pytest.raises(ValueError, match="must stay within the project root"):
        file_io.write_rms_simulator_csv(
            [make_wellbore_mapping()],
            relative_path,
        )


@pytest.mark.parametrize(
    "relative_path",
    [Path("../outside.renaming_table"), Path("/tmp/outside.renaming_table")],
)
def test_write_rms_simulator_renaming_table_rejects_paths_outside_project_root(
    fmu_dir: ProjectFMUDirectory,
    relative_path: Path,
    make_wellbore_mapping: Callable[..., InternalWellboreIdentifierMapping],
) -> None:
    """RMS renaming-table writes must reject paths outside the project root."""
    file_io = WellboreMappingsFileIO(fmu_dir)

    with pytest.raises(ValueError, match="must stay within the project root"):
        file_io.write_rms_simulator_renaming_table(
            [make_wellbore_mapping()],
            relative_path,
        )


@pytest.mark.parametrize(
    "relative_path",
    [
        Path("../outside_rms_pdm.renaming_table"),
        Path("/tmp/outside_rms_pdm.renaming_table"),
    ],
)
def test_write_rms_pdm_renaming_table_rejects_paths_outside_project_root(
    fmu_dir: ProjectFMUDirectory,
    relative_path: Path,
    make_wellbore_mapping: Callable[..., InternalWellboreIdentifierMapping],
) -> None:
    """RMS-to-PDM renaming-table writes must reject paths outside the root."""
    file_io = WellboreMappingsFileIO(fmu_dir)
    wellbore_mappings = [
        make_wellbore_mapping(
            source_system=DataSystem.rms,
            target_system=DataSystem.pdm,
            source_id="30_9-B-43_A",
            target_id="30/9-B-43 A",
        ),
    ]

    with pytest.raises(ValueError, match="must stay within the project root"):
        file_io.write_rms_pdm_renaming_table(
            wellbore_mappings,
            relative_path,
        )
