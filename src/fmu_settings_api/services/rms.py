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
        self, rms_project_path: Path
    ) -> tuple[RmsApiProxy, RmsApiProxy]:
        """Open an RMS project at the specified path.

        The RMS version is automatically detected from the project's .master file.

        Args:
            rms_project_path: Path to the RMS project configured in the .fmu config file

        Returns:
            RmsApiProxy: The opened RMS project proxy
        """
        version = self.get_rms_version(rms_project_path)

        rms_proxy = get_rmsapi(version=version)
        return rms_proxy, rms_proxy.Project.open(str(rms_project_path), readonly=True)

    def get_zones(self, rms_project: RmsApiProxy) -> list[RmsStratigraphicZone]:
        """Retrieve the zones from the RMS project.

        Args:
            rms_project: The opened RMS project proxy

        Returns:
            list[RmsStratigraphicZone]: List of zones in the project
        """
        return [
            RmsStratigraphicZone(
                name=zone.name.get(),
                top_horizon_name=zone.horizon_above.name.get(),
                base_horizon_name=zone.horizon_below.name.get(),
            )
            for zone in rms_project.zones
        ]

    def get_horizons(self, rms_project: RmsApiProxy) -> list[RmsHorizon]:
        """Retrieve all horizons from the RMS project.

        Args:
            rms_project: The opened RMS project proxy

        Returns:
            list[RmsHorizon]: List of horizons in the project
        """
        return [RmsHorizon(name=horizon.name.get()) for horizon in rms_project.horizons]

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
