"""Models related to RMS projects in a FMU project."""

from pathlib import Path

from pydantic import Field

from fmu_settings_api.models.common import BaseResponseModel


class RMSProjectPath(BaseResponseModel):
    """Path to an RMS project within the FMU project."""

    path: Path = Field(examples=["/path/to/some.project.rms.14.2.2"])
    """Absolute path to the RMS project within the FMU project."""


class RMSProjectPathsResult(BaseResponseModel):
    """List of RMS project paths within the FMU project."""

    results: list[RMSProjectPath]
    """List of absolute paths to RMS projects within the FMU project."""


class RmsStratigraphicZone(BaseResponseModel):
    """A stratigraphic zone from an RMS project."""

    name: str
    """Name of the zone."""

    top: str
    """Name of the horizon at the top of the zone."""

    base: str
    """Name of the horizon at the base of the zone."""


class RmsStratigraphicColumn(BaseResponseModel):
    """Stratigraphic column containing zones from an RMS project."""

    zones: list[RmsStratigraphicZone]
    """List of zones in the stratigraphic column."""


class Horizon(BaseResponseModel):
    """A horizon from an RMS project."""

    name: str
    """Name of the horizon."""


class HorizonList(BaseResponseModel):
    """List of horizons from an RMS project."""

    horizons: list[Horizon]
    """List of horizons in the project."""


class Well(BaseResponseModel):
    """A well from an RMS project."""

    name: str
    """Name of the well."""


class WellList(BaseResponseModel):
    """List of wells from an RMS project."""

    wells: list[Well]
    """List of wells in the project."""
