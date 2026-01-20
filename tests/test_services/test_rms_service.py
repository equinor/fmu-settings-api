"""Tests for the RMS service."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fmu.settings.models.project_config import (
    RmsCoordinateSystem,
    RmsHorizon,
    RmsStratigraphicZone,
    RmsWell,
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


def test_get_rms_version_from_project_master(rms_service: RmsService) -> None:
    """Test that the RMS version is read from the project's .master file."""
    rms_project_path = Path("/path/to/rms/project")
    master_rms_version = "13.0.3"

    mock_rms_config = MagicMock()
    mock_rms_config.version = master_rms_version

    with (
        patch(
            "fmu_settings_api.services.rms.RmsConfig",
            return_value=mock_rms_config,
        ) as mock_rms_config_class,
    ):
        rms_version = rms_service.get_rms_version(rms_project_path)

    mock_rms_config_class.assert_called_once_with(project=str(rms_project_path))
    assert rms_version == master_rms_version


def test_open_rms_project_success(rms_service: RmsService) -> None:
    """Test opening an RMS project successfully."""
    rms_project_path = Path("/path/to/rms/project")
    rms_version = "14.2.2"

    mock_rmsapi = MagicMock()
    mock_rmsapi.Project.open.return_value = "opened_project"

    with patch("fmu_settings_api.services.rms.get_rmsapi", return_value=mock_rmsapi):
        root, opened_project = rms_service.open_rms_project(
            rms_project_path, rms_version
        )

        mock_rmsapi.Project.open.assert_called_once_with(
            str(rms_project_path), readonly=True
        )
        assert root == mock_rmsapi
        assert opened_project == "opened_project"


def test_get_zones(rms_service: RmsService, mock_rms_proxy: MagicMock) -> None:
    """Test retrieving the zones."""
    zone_1 = MagicMock()
    zone_1.name.get.return_value = "Zone A"
    zone_1.horizon_above.name.get.return_value = "Top A"
    zone_1.horizon_below.name.get.return_value = "Base A"
    zone_2 = MagicMock()
    zone_2.name.get.return_value = "Zone B"
    zone_2.horizon_above.name.get.return_value = "Top B"
    zone_2.horizon_below.name.get.return_value = "Base B"
    mock_rms_proxy.zones = [zone_1, zone_2]
    mock_rms_proxy.__version__ = "1.11.0"

    zones = rms_service.get_zones(mock_rms_proxy)

    assert isinstance(zones, list)
    assert len(zones) == 2  # noqa: PLR2004
    assert all(isinstance(z, RmsStratigraphicZone) for z in zones)
    assert [z.name for z in zones] == ["Zone A", "Zone B"]
    assert [z.top_horizon_name for z in zones] == ["Top A", "Top B"]
    assert [z.base_horizon_name for z in zones] == ["Base A", "Base B"]


def test_get_zones_rms15(rms_service: RmsService, mock_rms_proxy: MagicMock) -> None:
    """Test retrieving zones when the RMS API supports stratigraphic columns."""
    zone_1 = MagicMock()
    zone_1.name.get.return_value = "Zone A"
    zone_1.horizon_above.name.get.return_value = "Top A"
    zone_1.horizon_below.name.get.return_value = "Base A"
    zone_2 = MagicMock()
    zone_2.name.get.return_value = "Zone B"
    zone_2.horizon_above.name.get.return_value = "Top B"
    zone_2.horizon_below.name.get.return_value = "Base B"

    mock_rms_proxy.__version__ = "1.12.0"
    mock_rms_proxy.zones.columns.return_value = ["Column1"]
    mock_rms_proxy.zones.column_zones.return_value = ["Zone A", "Zone B"]
    mock_rms_proxy.zones.__getitem__ = MagicMock(
        side_effect=lambda x: zone_1 if x == "Zone A" else zone_2
    )
    mock_rms_proxy.zones.__iter__ = MagicMock(return_value=iter([zone_1, zone_2]))

    zones = rms_service.get_zones(mock_rms_proxy)

    assert isinstance(zones, list)
    assert len(zones) == 2  # noqa: PLR2004
    assert all(isinstance(z, RmsStratigraphicZone) for z in zones)
    assert [z.name for z in zones] == ["Zone A", "Zone B"]
    assert [z.top_horizon_name for z in zones] == ["Top A", "Top B"]
    assert [z.base_horizon_name for z in zones] == ["Base A", "Base B"]
    assert all(z.stratigraphic_column_name == ["Column1"] for z in zones)


def test_get_zones_rms15_multiple_columns(
    rms_service: RmsService, mock_rms_proxy: MagicMock
) -> None:
    """Test retrieving zones where a zone exists in multiple stratigraphic columns."""
    zone_1 = MagicMock()
    zone_1.name.get.return_value = "Zone A"
    zone_1.horizon_above.name.get.return_value = "Top A"
    zone_1.horizon_below.name.get.return_value = "Base A"
    zone_2 = MagicMock()
    zone_2.name.get.return_value = "Zone B"
    zone_2.horizon_above.name.get.return_value = "Top B"
    zone_2.horizon_below.name.get.return_value = "Base B"

    mock_rms_proxy.__version__ = "1.12.0"
    mock_rms_proxy.zones.columns.return_value = ["Column1", "Column2"]

    def mock_column_zones(column_name: str) -> list[str]:
        if column_name == "Column1":
            return ["Zone A"]
        return ["Zone A", "Zone B"]

    mock_rms_proxy.zones.column_zones.side_effect = mock_column_zones
    mock_rms_proxy.zones.__getitem__ = MagicMock(
        side_effect=lambda x: zone_1 if x == "Zone A" else zone_2
    )
    mock_rms_proxy.zones.__iter__ = MagicMock(return_value=iter([zone_1, zone_2]))

    zones = rms_service.get_zones(mock_rms_proxy)

    assert isinstance(zones, list)
    assert len(zones) == 2  # noqa: PLR2004
    assert all(isinstance(z, RmsStratigraphicZone) for z in zones)

    zone_a = next(z for z in zones if z.name == "Zone A")
    assert zone_a.stratigraphic_column_name == ["Column1", "Column2"]

    zone_b = next(z for z in zones if z.name == "Zone B")
    assert zone_b.stratigraphic_column_name == ["Column2"]


def test_get_horizons(rms_service: RmsService, mock_rms_proxy: MagicMock) -> None:
    """Test retrieving horizons."""
    horizon_1 = MagicMock()
    horizon_1.name.get.return_value = "H1"
    horizon_1.type.name.get.return_value = "calculated"
    horizon_2 = MagicMock()
    horizon_2.name.get.return_value = "H2"
    horizon_2.type.name.get.return_value = "interpreted"
    mock_rms_proxy.horizons = [horizon_1, horizon_2]

    horizons = rms_service.get_horizons(mock_rms_proxy)

    assert isinstance(horizons, list)
    assert len(horizons) == 2  # noqa: PLR2004
    assert all(isinstance(h, RmsHorizon) for h in horizons)
    assert [h.name for h in horizons] == ["H1", "H2"]
    assert [h.type for h in horizons] == ["calculated", "interpreted"]


def test_get_wells(rms_service: RmsService, mock_rms_proxy: MagicMock) -> None:
    """Test retrieving wells."""
    well_1 = MagicMock()
    well_1.name.get.return_value = "W1"
    well_2 = MagicMock()
    well_2.name.get.return_value = "W2"
    mock_rms_proxy.wells = [well_1, well_2]

    wells = rms_service.get_wells(mock_rms_proxy)

    assert isinstance(wells, list)
    assert len(wells) == 2  # noqa: PLR2004
    assert all(isinstance(w, RmsWell) for w in wells)
    assert [w.name for w in wells] == ["W1", "W2"]


def test_get_coordinate_system(
    rms_service: RmsService, mock_rms_proxy: MagicMock
) -> None:
    """Test retrieving the coordinate system."""
    mock_cs = MagicMock()
    mock_cs.name.get.return_value = "westeros"
    mock_rms_proxy.coordinate_systems.get_project_coordinate_system.return_value = (
        mock_cs
    )

    coord_system = rms_service.get_coordinate_system(mock_rms_proxy)

    assert isinstance(coord_system, RmsCoordinateSystem)
    assert coord_system.name == "westeros"
