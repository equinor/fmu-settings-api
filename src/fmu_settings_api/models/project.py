"""Models pertaining to the .fmu directory."""

from pathlib import Path

from fmu.settings.models.project_config import ProjectConfig
from pydantic import BaseModel, Field


class FMUDirPath(BaseModel):
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


class GlobalConfigPath(BaseModel):
    """A relative path to a global config file, relative to the project root."""

    relative_path: Path = Field(examples=["relative_path/to/global_config_file"])
    """Relative path in the project to a global config file."""
