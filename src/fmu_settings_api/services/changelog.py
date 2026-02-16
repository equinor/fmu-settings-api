"""Service for managing changelog in .fmu and business logic."""

from pathlib import Path

from fmu.settings import ProjectFMUDirectory
from fmu.settings.models.change_info import ChangeInfo
from fmu.settings.models.log import Log


class ChangelogService:
    """Service for handling changelog."""

    def __init__(self, fmu_dir: ProjectFMUDirectory) -> None:
        """Initialize the service with a project FMU directory."""
        self._fmu_dir = fmu_dir

    @property
    def fmu_dir_path(self) -> Path:
        """Returns the path to the .fmu directory."""
        return self._fmu_dir.path

    def get_changelog(self) -> Log[ChangeInfo]:
        """Get the changelog as a list of change entries."""
        return self._fmu_dir.changelog.load()
