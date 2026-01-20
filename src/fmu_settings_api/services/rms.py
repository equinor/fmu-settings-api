"""Service for managing RMS projects through the RMS API."""

from pathlib import Path

from fmu.settings.models.project_config import (
    RmsCoordinateSystem,
    RmsHorizon,
    RmsStratigraphicZone,
    RmsWell,
)
from packaging.version import Version
from runrms import get_rmsapi
from runrms.api import RmsApiProxy
from runrms.config._rms_config import RmsConfig

MIN_RMS_API_VERSION_FOR_STRAT_COLUMNS = Version("1.12")


class RmsService:
    """Service for handling RMS projects."""

    @staticmethod
    def get_rms_version(rms_project_path: Path) -> str:
        """Get the RMS version from the project's .master file.

        Args:
            rms_project_path: Path to the RMS project

        Returns:
            str: The RMS version string (e.g., "14.2.2")
        """
        rms_config = RmsConfig(project=str(rms_project_path))
        return rms_config.version

    def open_rms_project(
        self, rms_project_path: Path, rms_version: str
    ) -> tuple[RmsApiProxy, RmsApiProxy]:
        """Open an RMS project at the specified Path with the specified RMS version.

        Args:
            rms_project_path: Path to the RMS project configured in the .fmu config file
            rms_version: RMS Version to use (e.g. "14.2.2" or "15.0.1.0")

        Returns:
            RmsApiProxy: The opened RMS project proxy
        """
        rms_proxy = get_rmsapi(version=rms_version)
        return rms_proxy, rms_proxy.Project.open(str(rms_project_path), readonly=True)

    def get_zones(self, rms_project: RmsApiProxy) -> list[RmsStratigraphicZone]:
        """Retrieve the zones from the RMS project.

        Args:
            rms_project: The opened RMS project proxy

        Returns:
            list[RmsStratigraphicZone]: List of zones in the project
        """
        zone_columns: dict[str, list[str]] = {}
        api_version = Version(rms_project.__version__)
        if api_version >= MIN_RMS_API_VERSION_FOR_STRAT_COLUMNS:
            for column_name in rms_project.zones.columns():
                for zonename in rms_project.zones.column_zones(column_name):
                    zone_columns.setdefault(zonename, []).append(column_name)

        zones = []
        for zone in rms_project.zones:
            if (
                zone.horizon_above.get() is not None
                and zone.horizon_below.get() is not None
            ):
                zone_name = zone.name.get()
                zones.append(
                    RmsStratigraphicZone(
                        name=zone_name,
                        top_horizon_name=zone.horizon_above.name.get(),
                        base_horizon_name=zone.horizon_below.name.get(),
                        stratigraphic_column_name=zone_columns.get(zone_name, [])
                        if zone_columns
                        else None,
                    )
                )

        return zones

    def get_horizons(self, rms_project: RmsApiProxy) -> list[RmsHorizon]:
        """Retrieve all horizons from the RMS project.

        Args:
            rms_project: The opened RMS project proxy

        Returns:
            list[RmsHorizon]: List of horizons in the project
        """
        return [
            RmsHorizon(
                name=horizon.name.get(),
                type=horizon.type.name.get(),
            )
            for horizon in rms_project.horizons
        ]

    def get_wells(self, rms_project: RmsApiProxy) -> list[RmsWell]:
        """Retrieve all wells from the RMS project.

        Args:
            rms_project: The opened RMS project proxy

        Returns:
            list[RmsWell]: List of wells in the project
        """
        return [RmsWell(name=well.name.get()) for well in rms_project.wells]

    def get_coordinate_system(self, rms_project: RmsApiProxy) -> RmsCoordinateSystem:
        """Retrieve the project coordinate system from the RMS project.

        Args:
            rms_project: The opened RMS project proxy

        Returns:
            RmsCoordinateSystem: The project coordinate system
        """
        cs = rms_project.coordinate_systems.get_project_coordinate_system()
        return RmsCoordinateSystem(name=cs.name.get())
