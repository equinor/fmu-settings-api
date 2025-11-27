"""Service for managing RMS projects through the RMS API."""

from pathlib import Path

from runrms import get_rmsapi
from runrms.api import RmsApiProxy
from runrms.config._rms_project import RmsProject

from fmu_settings_api.models.rms import (
    Horizon,
    HorizonList,
    RmsStratigraphicColumn,
    RmsStratigraphicZone,
    Well,
    WellList,
)


class RmsService:
    """Service for handling RMS projects."""

    def open_rms_project(self, rms_project_path: Path) -> RmsApiProxy:
        """Open an RMS project at the specified path.

        The RMS version is automatically detected from the project's .master file.

        Args:
            rms_project_path: Path to the RMS project configured in the .fmu config file

        Returns:
            RmsApiProxy: The opened RMS project proxy
        """
        rms_project_info = RmsProject.from_filepath(str(rms_project_path))
        version = rms_project_info.master.version

        rms_proxy = get_rmsapi(version=version)
        return rms_proxy.Project.open(str(rms_project_path), readonly=True)

    def get_strat_column(self, rms_project: RmsApiProxy) -> RmsStratigraphicColumn:
        """Retrieve the stratigraphic column from the RMS project.

        Args:
            rms_project: The opened RMS project proxy

        Returns:
            StratigraphicColumn: The stratigraphic column with zones
        """
        zones = []
        for zone in rms_project.zones:
            strat_zone = RmsStratigraphicZone(
                name=zone.name.get(),
                top=zone.horizon_above.name.get(),
                base=zone.horizon_below.name.get(),
            )
            zones.append(strat_zone)
        return RmsStratigraphicColumn(zones=zones)

    def get_horizons(self, rms_project: RmsApiProxy) -> HorizonList:
        """Retrieve all horizons from the RMS project.

        Args:
            rms_project: The opened RMS project proxy

        Returns:
            HorizonList: List of horizons in the project
        """
        horizons = []
        for horizon in rms_project.horizons:
            horizons.append(Horizon(name=horizon.name.get()))
        return HorizonList(horizons=horizons)

    def get_wells(self, rms_project: RmsApiProxy) -> WellList:
        """Retrieve all wells from the RMS project.

        Args:
            rms_project: The opened RMS project proxy

        Returns:
            WellList: List of wells in the project
        """
        wells = []
        for well in rms_project.wells:
            wells.append(Well(name=well.name.get()))
        return WellList(wells=wells)
