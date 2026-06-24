"""Service for managing changelog in .fmu and business logic."""

from pathlib import Path

from fmu.settings import ProjectFMUDirectory
from fmu.settings.models._enums import ChangeType
from fmu.settings.models.change_info import ChangeInfo
from fmu.settings.models.log import Filter, Log


class ChangelogService:
    """Service for handling changelog."""

    def __init__(self, fmu_dir: ProjectFMUDirectory) -> None:
        """Initialize the service with a project FMU directory."""
        self._fmu_dir = fmu_dir

    @property
    def fmu_dir_path(self) -> Path:
        """Returns the path to the .fmu directory."""
        return self._fmu_dir.path

    def get_changelog(
        self,
        change_type: ChangeType | None = None,
        filter_: Filter | None = None,
        max_entries: int | None = None,
    ) -> Log[ChangeInfo]:
        """Get changelog entries with optional filtering and entry limit."""
        changelog = (
            self._fmu_dir.changelog.filter_log(filter_)
            if filter_ is not None
            else self._fmu_dir.changelog.load()
        )

        if change_type is not None:
            changelog = Log(
                [entry for entry in changelog if entry.change_type == change_type]
            )

        if max_entries is not None:
            changelog = Log(list(changelog)[-max_entries:])

        return changelog
