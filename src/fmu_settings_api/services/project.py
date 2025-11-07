"""Service for managing FMU project operations and business logic."""

from pathlib import Path

from fmu.datamodels.fmu_results.fields import Access, Model, Smda
from fmu.settings import ProjectFMUDirectory
from fmu.settings._global_config import find_global_config

from fmu_settings_api.models import FMUProject
from fmu_settings_api.models.project import GlobalConfigPath


class ProjectService:
    """Service for handling FMU project business logic."""

    def __init__(self, fmu_dir: ProjectFMUDirectory) -> None:
        """Initialize the service with a project FMU directory."""
        self._fmu_dir = fmu_dir

    def get_project_data(self) -> FMUProject:
        """Get the paths and configuration of the project FMU directory."""
        is_read_only = not self._fmu_dir._lock.is_acquired()

        return FMUProject(
            path=self._fmu_dir.base_path,
            project_dir_name=self._fmu_dir.base_path.name,
            config=self._fmu_dir.config.load(),
            is_read_only=is_read_only,
        )

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

    def update_masterdata(self, smda_masterdata: Smda) -> tuple[bool, Path]:
        """Save SMDA masterdata to the project FMU directory."""
        self._fmu_dir.set_config_value("masterdata.smda", smda_masterdata.model_dump())
        return True, self._fmu_dir.path

    def update_model(self, model: Model) -> tuple[bool, Path]:
        """Save model data to the project FMU directory."""
        self._fmu_dir.set_config_value("model", model.model_dump())
        return True, self._fmu_dir.path

    def update_access(self, access: Access) -> tuple[bool, Path]:
        """Save access data to the project FMU directory."""
        self._fmu_dir.set_config_value("access", access.model_dump())
        return True, self._fmu_dir.path
