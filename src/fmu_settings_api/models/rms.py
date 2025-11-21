"""Models related to RMS projects in a FMU project."""

from pathlib import Path

from pydantic import Field

from fmu_settings_api.models.common import BaseResponseModel


class RMSProjectPath(BaseResponseModel):
    """Path to an RMS project within the FMU project."""

    rms_project_path: Path = Field(examples=["/path/to/some.project.rms.14.2.2"])
    """Absolute path to the RMS project within the FMU project."""


class RMSProjectPathsResult(BaseResponseModel):
    """List of RMS project paths within the FMU project."""

    rms_project_paths: list[RMSProjectPath]
    """List of absolute paths to RMS projects within the FMU project."""
