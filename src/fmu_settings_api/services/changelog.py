"""Service for managing changelog in .fmu and business logic."""

from pathlib import Path

from fmu.settings import ProjectFMUDirectory
from fmu.settings.models._enums import ChangeType
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

    def get_changelog(self, filtertype: ChangeType | None = None) -> Log[ChangeInfo]:
        """Get changelog entries, optionally filtered by change type."""
        changelog = self._fmu_dir.changelog.load()
        return self._filter_by_change_type(changelog, filtertype)

    @staticmethod
    def _filter_by_change_type(
        changelog: Log[ChangeInfo],
        filtertype: ChangeType | None,
    ) -> Log[ChangeInfo]:
        """Filter changelog entries by change type when provided."""
        if filtertype is None:
            return changelog

        return Log([entry for entry in changelog if entry.change_type == filtertype])
