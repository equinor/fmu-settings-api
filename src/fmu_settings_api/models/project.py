"""Models pertaining to the .fmu directory."""

from pathlib import Path

from fmu.settings.models.lock_info import LockInfo
from fmu.settings.models.project_config import ProjectConfig
from pydantic import Field

from fmu_settings_api.models.common import BaseResponseModel


class FMUDirPath(BaseResponseModel):
    """Path where a .fmu directory may exist."""

    path: Path = Field(examples=["/path/to/project.2038.02.02"])
    """Absolute path to the directory which maybe contains a .fmu directory."""


class FMUProject(FMUDirPath):
    """Information returned when 'opening' an FMU Directory."""

    project_dir_name: str = Field(examples=["project.2038.02.02"])
    """The directory name, not the path, that contains the .fmu directory."""

    config: ProjectConfig
    """The configuration of an FMU project's .fmu directory."""

    is_read_only: bool = Field(default=False)
    """Whether the project is in read-only mode due to lock conflicts."""


class GlobalConfigPath(BaseResponseModel):
    """A relative path to a global config file, relative to the project root."""

    relative_path: Path = Field(examples=["relative_path/to/global_config_file"])
    """Relative path in the project to a global config file."""


class LockStatus(BaseResponseModel):
    """Information about the project lock status."""

    is_lock_acquired: bool
    """Whether the current session holds the write lock."""

    lock_file_exists: bool
    """Whether a lock file exists."""

    lock_info: LockInfo | None = Field(default=None)
    """Contents of the lock file, if available and readable."""

    lock_status_error: str | None = Field(default=None)
    """Error message if checking lock status failed."""

    lock_file_read_error: str | None = Field(default=None)
    """Error message if reading the lock file failed."""

    last_lock_acquire_error: str | None = Field(default=None)
    """Error message from the last attempt to acquire the lock."""

    last_lock_release_error: str | None = Field(default=None)
    """Error message from the last attempt to release the lock."""

    last_lock_refresh_error: str | None = Field(default=None)
    """Error message from the last attempt to refresh the lock."""
