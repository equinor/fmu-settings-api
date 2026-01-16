"""Service for managing RMS projects through the RMS API."""

from pathlib import Path

from fmu.settings.models.project_config import (
    RmsCoordinateSystem,
    RmsHorizon,
    RmsStratigraphicZone,
    RmsWell,
)
from runrms import get_rmsapi
from runrms.api import RmsApiProxy
from runrms.config._rms_project import RmsProject


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
        rms_project_info = RmsProject.from_filepath(str(rms_project_path))
        return rms_project_info.master.version

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

    def get_zones(
        self, rms_project: RmsApiProxy, rms_version: str
    ) -> list[RmsStratigraphicZone]:
        """Retrieve the zones from the RMS project.

        Args:
            rms_project: The opened RMS project proxy
            rms_version: RMS Version to use (e.g. "14.2.2" or "15.0.1.0")

        Returns:
            list[RmsStratigraphicZone]: List of zones in the project
        """
        # RMS 15+ supports stratigraphic columns
        if rms_version.startswith("15."):
            zones_dict: dict[tuple[str, str, str], list[str]] = {}
            for column_name in rms_project.zones.columns():
                for zonename in rms_project.zones.column_zones(column_name):
                    zone = rms_project.zones[zonename]
                    if zone.horizon_above is None or zone.horizon_below is None:
                        continue

                    zone_key = (
                        zone.name.get(),
                        zone.horizon_above.name.get(),
                        zone.horizon_below.name.get(),
                    )
                    zones_dict.setdefault(zone_key, []).append(column_name)

            return [
                RmsStratigraphicZone(
                    name=name,
                    top_horizon_name=top_horizon,
                    base_horizon_name=base_horizon,
                    stratigraphic_column_name=column_names,
                )
                for (
                    name,
                    top_horizon,
                    base_horizon,
                ), column_names in zones_dict.items()
            ]
        # RMS 14 and earlier don't support stratigraphic columns
        return [
            RmsStratigraphicZone(
                name=zone.name.get(),
                top_horizon_name=zone.horizon_above.name.get(),
                base_horizon_name=zone.horizon_below.name.get(),
            )
            for zone in rms_project.zones
            if zone.horizon_above is not None and zone.horizon_below is not None
        ]

    def get_horizons(self, rms_project: RmsApiProxy) -> list[RmsHorizon]:
        """Retrieve all horizons from the RMS project.

        Args:
            rms_project: The opened RMS project proxy

        Returns:
            list[RmsHorizon]: List of horizons in the project
        """
        horizons = []
        for horizon in rms_project.horizons:
            horizon_type = horizon.type.get()
            type_str = str(horizon_type).split(".")[-1]
            horizons.append(
                RmsHorizon(
                    name=horizon.name.get(),
                    type=type_str,  # type: ignore[arg-type]
                )
            )
        return horizons

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
