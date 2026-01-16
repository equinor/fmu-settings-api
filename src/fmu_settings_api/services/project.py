"""Service for managing FMU project operations and business logic."""

from pathlib import Path

from fmu.datamodels.common import Access, Smda
from fmu.datamodels.fmu_results.fields import Model
from fmu.settings import ProjectFMUDirectory
from fmu.settings._global_config import find_global_config
from fmu.settings.models.project_config import (
    RmsCoordinateSystem,
    RmsHorizon,
    RmsStratigraphicZone,
    RmsWell,
)

from fmu_settings_api.models import FMUProject
from fmu_settings_api.models.project import GlobalConfigPath

from .rms import RmsService


class ProjectService:
    """Service for handling FMU project business logic."""

    def __init__(self, fmu_dir: ProjectFMUDirectory) -> None:
        """Initialize the service with a project FMU directory."""
        self._fmu_dir = fmu_dir

    def get_project_data(self) -> FMUProject:
        """Get the paths and configuration of the project FMU directory."""
        return FMUProject(
            path=self._fmu_dir.base_path,
            project_dir_name=self._fmu_dir.base_path.name,
            config=self._fmu_dir.config.load(),
        )

    @property
    def fmu_dir_path(self) -> Path:
        """Returns the path to the .fmu directory."""
        return self._fmu_dir.path

    @property
    def config_path(self) -> Path:
        """Returns the path to the project config file."""
        return self._fmu_dir.config.path

    @property
    def rms_project_path(self) -> Path | None:
        """Returns the path to the RMS project from the config file."""
        return self._fmu_dir.get_config_value("rms.path", None)

    def check_valid_global_config(self) -> None:
        """Check if a valid global config exists at the default location."""
        project_root = self._fmu_dir.path.parent
        existing_config = find_global_config(project_root)

        if existing_config is None:
            raise FileNotFoundError("No valid global config file found in the project.")

    def import_global_config(self, path: GlobalConfigPath | None = None) -> None:
        """Load the global config into the project masterdata."""
        if self._fmu_dir.config.load().masterdata is not None:
            raise FileExistsError("Masterdata exists in the project config.")

        project_root = self._fmu_dir.path.parent
        extra_output_paths = None

        if path is not None:
            global_config_path = project_root / path.relative_path
            extra_output_paths = [global_config_path]

        global_config = find_global_config(
            project_root, extra_output_paths=extra_output_paths
        )

        if global_config is None:
            raise FileNotFoundError("No valid global config file found in the project.")

        self._fmu_dir.set_config_value(
            "masterdata", global_config.masterdata.model_dump()
        )

    def update_masterdata(self, smda_masterdata: Smda) -> bool:
        """Save SMDA masterdata to the project FMU directory."""
        self._fmu_dir.set_config_value("masterdata.smda", smda_masterdata.model_dump())
        return True

    def update_model(self, model: Model) -> bool:
        """Save model data to the project FMU directory."""
        self._fmu_dir.set_config_value("model", model.model_dump())
        return True

    def update_access(self, access: Access) -> bool:
        """Save access data to the project FMU directory."""
        self._fmu_dir.set_config_value("access", access.model_dump())
        return True

    def get_rms_projects(self) -> list[Path]:
        """Get the paths of RMS projects in this project directory."""
        return self._fmu_dir.find_rms_projects()

    def update_rms(self, rms_project_path: Path) -> str:
        """Save the RMS project path and version in the project FMU directory."""
        try:
            rms_version = RmsService.get_rms_version(rms_project_path)
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"RMS project path {rms_project_path} does not exist."
            ) from e

        self._fmu_dir.update_config(
            {
                "rms.path": rms_project_path,
                "rms.version": rms_version,
            }
        )

        return rms_version

    def _ensure_rms_config_exists(self) -> None:
        """Ensure RMS config exists before updating individual fields."""
        rms_config = self._fmu_dir.get_config_value("rms", None)
        if rms_config is None:
            raise ValueError(
                "RMS project path must be set before updating RMS fields. "
                "Use PATCH /project/rms first."
            )

    def update_rms_coordinate_system(
        self, coordinate_system: RmsCoordinateSystem
    ) -> bool:
        """Save RMS coordinate system to the project FMU directory."""
        self._ensure_rms_config_exists()
        self._fmu_dir.set_config_value(
            "rms.coordinate_system", coordinate_system.model_dump()
        )
        return True

    def update_rms_zones(self, zones: list[RmsStratigraphicZone]) -> bool:
        """Save RMS zones to the project FMU directory."""
        self._ensure_rms_config_exists()
        self._fmu_dir.set_config_value(
            "rms.zones", [zone.model_dump() for zone in zones]
        )
        return True

    def update_rms_horizons(self, horizons: list[RmsHorizon]) -> bool:
        """Save RMS horizons to the project FMU directory."""
        self._ensure_rms_config_exists()
        self._fmu_dir.set_config_value(
            "rms.horizons", [horizon.model_dump() for horizon in horizons]
        )
        return True

    def update_rms_wells(self, wells: list[RmsWell]) -> bool:
        """Save RMS wells to the project FMU directory."""
        self._ensure_rms_config_exists()
        self._fmu_dir.set_config_value(
            "rms.wells", [well.model_dump() for well in wells]
        )
        return True
