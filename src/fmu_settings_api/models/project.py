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
