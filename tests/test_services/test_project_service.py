"""Tests for ProjectService."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fmu.settings import ProjectFMUDirectory
from fmu.settings.models.project_config import (
    RmsCoordinateSystem,
    RmsHorizon,
    RmsStratigraphicZone,
    RmsWell,
)

from fmu_settings_api.services.project import ProjectService


def test_rms_project_path_returns_path(fmu_dir: ProjectFMUDirectory) -> None:
    """Test that rms_project_path property returns the path from config."""
    expected_path = Path("/path/to/rms/project")
    service = ProjectService(fmu_dir)
    fmu_dir.set_config_value("rms", {"path": expected_path, "version": "14.2.2"})

    assert service.rms_project_path == expected_path


def test_rms_project_path_returns_none(fmu_dir: ProjectFMUDirectory) -> None:
    """Test that rms_project_path property returns None when not set."""
    service = ProjectService(fmu_dir)

    assert service.rms_project_path is None


def test_update_rms_saves_path_and_version(fmu_dir: ProjectFMUDirectory) -> None:
    """Test that update_rms saves the RMS project path and version."""
    rms_project_path = Path("/path/to/rms/project.rms14.2.2")
    service = ProjectService(fmu_dir)

    with patch(
        "fmu_settings_api.services.project.RmsService.get_rms_version",
        return_value="14.2.2",
    ):
        rms_version = service.update_rms(rms_project_path)

    assert rms_version == "14.2.2"
    saved_config = fmu_dir.config.load().rms
    assert saved_config is not None
    assert saved_config.path == rms_project_path
    assert saved_config.version == "14.2.2"


def test_update_rms_preserves_existing_fields(fmu_dir: ProjectFMUDirectory) -> None:
    """Test that update_rms preserves existing RMS fields when updating path/version."""
    service = ProjectService(fmu_dir)

    coordinate_system = RmsCoordinateSystem(name="westeros")
    zone = RmsStratigraphicZone(
        name="Zone1", top_horizon_name="TopZone1", base_horizon_name="BaseZone1"
    )
    horizon = RmsHorizon(name="TopReservoir", type="calculated")
    well = RmsWell(name="Well-1")

    fmu_dir.set_config_value(
        "rms",
        {
            "path": Path("/old/path/project.rms13.1.0"),
            "version": "13.1.0",
            "coordinate_system": coordinate_system.model_dump(),
            "zones": [zone.model_dump()],
            "horizons": [horizon.model_dump()],
            "wells": [well.model_dump()],
        },
    )

    new_rms_project_path = Path("/new/path/project.rms14.2.2")
    with patch(
        "fmu_settings_api.services.project.RmsService.get_rms_version",
        return_value="14.2.2",
    ):
        rms_version = service.update_rms(new_rms_project_path)

    assert rms_version == "14.2.2"
    saved_config = fmu_dir.config.load().rms
    assert saved_config is not None
    assert saved_config.path == new_rms_project_path
    assert saved_config.version == "14.2.2"

    assert saved_config.coordinate_system is not None
    assert saved_config.coordinate_system.name == "westeros"
    assert saved_config.zones is not None
    assert saved_config.zones[0].name == "Zone1"
    assert saved_config.horizons is not None
    assert saved_config.horizons[0].name == "TopReservoir"
    assert saved_config.wells is not None
    assert saved_config.wells[0].name == "Well-1"


def test_rms_project_path_missing_path_value(fmu_dir: ProjectFMUDirectory) -> None:
    """Test that rms_project_path returns None when rms config lacks a path."""
    service = ProjectService(fmu_dir)

    with patch.object(fmu_dir, "get_config_value", return_value=None) as mock_get:
        assert service.rms_project_path is None
        mock_get.assert_called_once_with("rms.path", None)


def test_update_rms_missing_project_path_raises_file_not_found(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test update_rms raises FileNotFoundError when RMS path is missing."""
    rms_project_path = Path("/path/to/rms/project.rms14.2.2")
    service = ProjectService(fmu_dir)

    with (
        patch(
            "fmu_settings_api.services.project.RmsService.get_rms_version",
            side_effect=FileNotFoundError("not found"),
        ),
        pytest.raises(FileNotFoundError) as exc_info,
    ):
        service.update_rms(rms_project_path)

    assert "does not exist" in str(exc_info.value)
    assert fmu_dir.config.load().rms is None


def test_ensure_rms_config_exists_raises_when_not_set(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test that _ensure_rms_config_exists raises ValueError when RMS not set."""
    service = ProjectService(fmu_dir)

    with pytest.raises(ValueError) as exc_info:
        service._ensure_rms_config_exists()

    assert "RMS project path must be set" in str(exc_info.value)


def test_ensure_rms_config_exists_passes_when_set(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test that _ensure_rms_config_exists passes when RMS config is set."""
    service = ProjectService(fmu_dir)
    fmu_dir.set_config_value("rms", {"path": "/some/path", "version": "14.2.2"})

    # Should not raise
    service._ensure_rms_config_exists()


def test_update_rms_coordinate_system_success(fmu_dir: ProjectFMUDirectory) -> None:
    """Test saving RMS coordinate system to config."""
    service = ProjectService(fmu_dir)
    fmu_dir.set_config_value("rms", {"path": "/some/path", "version": "14.2.2"})

    coord_system = RmsCoordinateSystem(name="westeros")
    result = service.update_rms_coordinate_system(coord_system)

    assert result is True
    saved_config = fmu_dir.config.load().rms
    assert saved_config is not None
    assert saved_config.coordinate_system is not None
    assert saved_config.coordinate_system.name == "westeros"


def test_update_rms_coordinate_system_requires_rms_config(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test that updating coordinate system requires RMS config to be set."""
    service = ProjectService(fmu_dir)
    coord_system = RmsCoordinateSystem(name="westeros")

    with pytest.raises(ValueError) as exc_info:
        service.update_rms_coordinate_system(coord_system)

    assert "RMS project path must be set" in str(exc_info.value)


def test_update_rms_stratigraphic_framework_success(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test saving RMS zones and horizons to config."""
    service = ProjectService(fmu_dir)
    fmu_dir.set_config_value("rms", {"path": "/some/path", "version": "14.2.2"})

    zones = [
        RmsStratigraphicZone(
            name="Zone A", top_horizon_name="Top A", base_horizon_name="Base A"
        ),
        RmsStratigraphicZone(
            name="Zone B", top_horizon_name="Top B", base_horizon_name="Base B"
        ),
    ]
    horizons = [
        RmsHorizon(name="Top A", type="calculated"),
        RmsHorizon(name="Base A", type="calculated"),
        RmsHorizon(name="Top B", type="interpreted"),
        RmsHorizon(name="Base B", type="interpreted"),
    ]
    result = service.update_rms_stratigraphic_framework(zones, horizons)

    assert result is True
    saved_config = fmu_dir.config.load().rms
    assert saved_config is not None
    assert saved_config.zones is not None
    assert saved_config.horizons is not None
    assert len(saved_config.zones) == 2  # noqa: PLR2004
    assert len(saved_config.horizons) == 4  # noqa: PLR2004
    assert [zone.name for zone in saved_config.zones] == ["Zone A", "Zone B"]
    assert [horizon.name for horizon in saved_config.horizons] == [
        "Top A",
        "Base A",
        "Top B",
        "Base B",
    ]


def test_update_rms_stratigraphic_framework_requires_rms_config(
    fmu_dir: ProjectFMUDirectory,
) -> None:
    """Test that updating stratigraphic framework requires RMS config to be set."""
    service = ProjectService(fmu_dir)
    zones = [
        RmsStratigraphicZone(
            name="Zone A", top_horizon_name="Top", base_horizon_name="Base"
        )
    ]
    horizons = [
        RmsHorizon(name="Top", type="calculated"),
        RmsHorizon(name="Base", type="calculated"),
    ]

    with pytest.raises(ValueError) as exc_info:
        service.update_rms_stratigraphic_framework(zones, horizons)

    assert "RMS project path must be set" in str(exc_info.value)


def test_update_rms_wells_success(fmu_dir: ProjectFMUDirectory) -> None:
    """Test saving RMS wells to config."""
    service = ProjectService(fmu_dir)
    fmu_dir.set_config_value("rms", {"path": "/some/path", "version": "14.2.2"})

    wells = [RmsWell(name="W1"), RmsWell(name="W2")]
    result = service.update_rms_wells(wells)

    assert result is True
    saved_config = fmu_dir.config.load().rms
    assert saved_config is not None
    assert saved_config.wells is not None
    assert len(saved_config.wells) == 2  # noqa: PLR2004
    assert [w.name for w in saved_config.wells] == ["W1", "W2"]


def test_update_rms_wells_requires_rms_config(fmu_dir: ProjectFMUDirectory) -> None:
    """Test that updating wells requires RMS config to be set."""
    service = ProjectService(fmu_dir)
    wells = [RmsWell(name="W1")]

    with pytest.raises(ValueError) as exc_info:
        service.update_rms_wells(wells)

    assert "RMS project path must be set" in str(exc_info.value)


def test_update_rms_fields_preserves_other_fields(fmu_dir: ProjectFMUDirectory) -> None:
    """Test that updating one RMS field preserves other fields."""
    service = ProjectService(fmu_dir)
    fmu_dir.set_config_value("rms", {"path": "/some/path", "version": "14.2.2"})

    coord_system = RmsCoordinateSystem(name="westeros")
    service.update_rms_coordinate_system(coord_system)

    zones = [
        RmsStratigraphicZone(
            name="Zone A", top_horizon_name="Top A", base_horizon_name="Base A"
        )
    ]
    horizons = [
        RmsHorizon(name="Top A", type="calculated"),
        RmsHorizon(name="Base A", type="calculated"),
    ]
    service.update_rms_stratigraphic_framework(zones, horizons)

    saved_config = fmu_dir.config.load().rms
    assert saved_config is not None
    assert saved_config.coordinate_system is not None
    assert saved_config.coordinate_system.name == "westeros"
    assert saved_config.horizons is not None
    assert [h.name for h in saved_config.horizons] == ["Top A", "Base A"]
    assert saved_config.zones is not None
    assert saved_config.zones[0].name == "Zone A"
    assert str(saved_config.path) == "/some/path"
    assert saved_config.version == "14.2.2"
