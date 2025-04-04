"""Models pertaining to the .fmu directory."""

from pathlib import Path

from pydantic import BaseModel


class FMUDirPath(BaseModel):
    """Path where a .fmu directory may exist."""

    path: Path
    """Path to the directory which should or will contain a .fmu directory."""
