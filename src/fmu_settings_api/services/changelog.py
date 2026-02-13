"""Service for managing changelog in .fmu and business logic."""

from fmu.settings import ProjectFMUDirectory
from fmu.settings.models.change_info import ChangeInfo
from fmu.settings.models.log import Log


class ChangelogService:
    """Service for handling changelog."""

    def __init__(self, fmu_dir: ProjectFMUDirectory) -> None:
        """Initialize the service with a project FMU directory."""
        self._fmu_dir = fmu_dir

    def get_changelog(self) -> Log[ChangeInfo]:
        """Get the changelog as a list of change entries."""
        return self._fmu_dir.changelog.load()
