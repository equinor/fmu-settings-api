"""Models related to RMS projects in a FMU project."""

from pathlib import Path

from pydantic import Field

from fmu_settings_api.models.common import BaseResponseModel


class RmsProjectPath(BaseResponseModel):
    """Path to an RMS project within the FMU project."""

    path: Path = Field(examples=["/path/to/some.project.rms.14.2.2"])
    """Absolute path to the RMS project within the FMU project."""


class RmsProjectPathsResult(BaseResponseModel):
    """List of RMS project paths within the FMU project."""

    results: list[RmsProjectPath]
    """List of absolute paths to RMS projects within the FMU project."""


class RmsVersion(BaseResponseModel):
    """RMS version."""

    version: str = Field(examples=["14.2.2", "15.0.1.0"])
    """A version of RMS."""
