"""Models related to RMS projects in a FMU project."""

from pathlib import Path

from fmu.settings.models.project_config import RmsHorizon, RmsStratigraphicZone
from pydantic import Field, model_validator

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


class RmsStratigraphicFramework(BaseResponseModel):
    """RMS stratigraphic framework consisting of zones and horizons."""

    zones: list[RmsStratigraphicZone]
    """List of RMS stratigraphic zones."""

    horizons: list[RmsHorizon]
    """List of RMS horizons."""

    @model_validator(mode="after")
    def validate_zone_horizons(self) -> "RmsStratigraphicFramework":
        """Ensure zones reference horizons provided in the same request."""
        horizon_names = {horizon.name for horizon in self.horizons}

        referenced_horizons = {
            horizon_name
            for zone in self.zones
            for horizon_name in (zone.top_horizon_name, zone.base_horizon_name)
        }

        missing_horizons = referenced_horizons - horizon_names

        if missing_horizons:
            missing_list = ", ".join(sorted(missing_horizons))
            raise ValueError(
                f"RMS zones reference horizons not present in request: {missing_list}"
            )

        return self
