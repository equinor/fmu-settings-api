"""Service for managing RMS projects through the RMS API."""

from pathlib import Path

from runrms import get_rmsapi
from runrms.api import RmsApiProxy
from runrms.config._rms_project import RmsProject

from fmu_settings_api.models.rms import (
    RmsHorizon,
    RmsHorizonList,
    RmsStratigraphicZone,
    RmsWell,
    RmsWellList,
    RmsZoneList,
)


class RmsService:
    """Service for handling RMS projects."""

    def get_rms_version(self, rms_project_path: Path) -> str:
        """Get the RMS version from the project's .master file.

        Args:
            rms_project_path: Path to the RMS project

        Returns:
            str: The RMS version string (e.g., "14.2.2")
        """
        rms_project_info = RmsProject.from_filepath(str(rms_project_path))
        return rms_project_info.master.version

    def open_rms_project(self, rms_project_path: Path) -> RmsApiProxy:
        """Open an RMS project at the specified path.

        The RMS version is automatically detected from the project's .master file.

        Args:
            rms_project_path: Path to the RMS project configured in the .fmu config file

        Returns:
            RmsApiProxy: The opened RMS project proxy
        """
        version = self.get_rms_version(rms_project_path)

        rms_proxy = get_rmsapi(version=version)
        return rms_proxy.Project.open(str(rms_project_path), readonly=True)

    def get_zones(self, rms_project: RmsApiProxy) -> RmsZoneList:
        """Retrieve the zones from the RMS project.

        Args:
            rms_project: The opened RMS project proxy

        Returns:
            RmsZoneList: List of zones in the project
        """
        zones = [
            RmsStratigraphicZone(
                name=zone.name.get(),
                top=zone.horizon_above.name.get(),
                base=zone.horizon_below.name.get(),
            )
            for zone in rms_project.zones
        ]
        return RmsZoneList(zones=zones)

    def get_horizons(self, rms_project: RmsApiProxy) -> RmsHorizonList:
        """Retrieve all horizons from the RMS project.

        Args:
            rms_project: The opened RMS project proxy

        Returns:
            RmsHorizonList: List of horizons in the project
        """
        horizons = [
            RmsHorizon(name=horizon.name.get()) for horizon in rms_project.horizons
        ]
        return RmsHorizonList(horizons=horizons)

    def get_wells(self, rms_project: RmsApiProxy) -> RmsWellList:
        """Retrieve all wells from the RMS project.

        Args:
            rms_project: The opened RMS project proxy

        Returns:
            RmsWellList: List of wells in the project
        """
        wells = [RmsWell(name=well.name.get()) for well in rms_project.wells]
        return RmsWellList(wells=wells)
