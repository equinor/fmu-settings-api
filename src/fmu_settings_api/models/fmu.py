"""Models pertaining to the .fmu directory."""

from pathlib import Path

from fmu.settings.models.project_config import ProjectConfig
from pydantic import BaseModel


class FMUDirPath(BaseModel):
    """Path where a .fmu directory may exist."""

    path: Path
    """Path to the directory which should or will contain a .fmu directory."""


class FMUProject(FMUDirPath):
    """Information returned when 'opening' an FMU Directory."""

    project_dir_name: str
    config: ProjectConfig
    """The configuration of an FMU project's .fmu directory."""
