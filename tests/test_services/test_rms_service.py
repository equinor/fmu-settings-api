"""Tests for the RMS service."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fmu_settings_api.models.rms import (
    HorizonList,
    RmsStratigraphicColumn,
    WellList,
)
from fmu_settings_api.services.rms import RmsService


@pytest.fixture
def rms_service() -> RmsService:
    """Returns an RmsService instance."""
    return RmsService()


@pytest.fixture
def mock_rms_proxy() -> MagicMock:
    """Returns a mock RMS API proxy."""
    return MagicMock()


def test_open_rms_project_success(rms_service: RmsService) -> None:
    """Test opening an RMS project successfully."""
    rms_project_path = Path("/path/to/rms/project")

    mock_rms_project_info = MagicMock()
    mock_rms_project_info.master.version = "14.2.2"

    mock_rmsapi = MagicMock()
    mock_rmsapi.Project.open.return_value = "opened_project"

    with (
        patch(
            "fmu_settings_api.services.rms.RmsProject.from_filepath",
            return_value=mock_rms_project_info,
        ),
        patch("fmu_settings_api.services.rms.get_rmsapi", return_value=mock_rmsapi),
    ):
        opened_project = rms_service.open_rms_project(rms_project_path)

        mock_rmsapi.Project.open.assert_called_once_with(
            str(rms_project_path), readonly=True
        )
        assert opened_project == "opened_project"


def test_open_rms_project_reads_version_from_master(rms_service: RmsService) -> None:
    """Test that the RMS version is read from the project's .master file."""
    rms_project_path = Path("/path/to/rms/project")

    mock_rms_project_info = MagicMock()
    mock_rms_project_info.master.version = "13.0.3"

    mock_rmsapi = MagicMock()

    with (
        patch(
            "fmu_settings_api.services.rms.RmsProject.from_filepath",
            return_value=mock_rms_project_info,
        ) as mock_from_filepath,
        patch(
            "fmu_settings_api.services.rms.get_rmsapi", return_value=mock_rmsapi
        ) as mock_get_rmsapi,
    ):
        rms_service.open_rms_project(rms_project_path)

        mock_from_filepath.assert_called_once_with(str(rms_project_path))
        mock_get_rmsapi.assert_called_once_with(version="13.0.3")


def test_get_strat_column(rms_service: RmsService, mock_rms_proxy: MagicMock) -> None:
    """Test retrieving the stratigraphic column."""
    zone = MagicMock()
    zone.name.get.return_value = "Zone A"
    zone.horizon_above.name.get.return_value = "Top"
    zone.horizon_below.name.get.return_value = "Base"
    mock_rms_proxy.zones = [zone]

    strat_column = rms_service.get_strat_column(mock_rms_proxy)

    assert isinstance(strat_column, RmsStratigraphicColumn)
    assert strat_column.zones[0].name == "Zone A"
    assert strat_column.zones[0].top == "Top"
    assert strat_column.zones[0].base == "Base"


def test_get_horizons(rms_service: RmsService, mock_rms_proxy: MagicMock) -> None:
    """Test retrieving horizons."""
    horizon_1 = MagicMock()
    horizon_1.name.get.return_value = "H1"
    horizon_2 = MagicMock()
    horizon_2.name.get.return_value = "H2"
    mock_rms_proxy.horizons = [horizon_1, horizon_2]

    horizons = rms_service.get_horizons(mock_rms_proxy)

    assert isinstance(horizons, HorizonList)
    assert [h.name for h in horizons.horizons] == ["H1", "H2"]


def test_get_wells(rms_service: RmsService, mock_rms_proxy: MagicMock) -> None:
    """Test retrieving wells."""
    well_1 = MagicMock()
    well_1.name.get.return_value = "W1"
    well_2 = MagicMock()
    well_2.name.get.return_value = "W2"
    mock_rms_proxy.wells = [well_1, well_2]

    wells = rms_service.get_wells(mock_rms_proxy)

    assert isinstance(wells, WellList)
    assert [w.name for w in wells.wells] == ["W1", "W2"]
