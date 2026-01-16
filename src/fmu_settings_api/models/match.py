"""Models for matching."""

from typing import Literal

from fmu.datamodels.common.masterdata import CoordinateSystem
from fmu.settings.models.project_config import RmsCoordinateSystem, RmsStratigraphicZone
from pydantic import Field

from fmu_settings_api.models.common import BaseResponseModel

from .smda import StratigraphicUnit


class RmsStratigraphyMatch(BaseResponseModel):
    """A matched pair of RMS zone and SMDA stratigraphic unit."""

    rms_zone: RmsStratigraphicZone
    """The RMS stratigraphic zone."""

    smda_unit: StratigraphicUnit
    """The matched SMDA stratigraphic unit."""

    score: float = Field(ge=0, le=100)
    """Similarity score for the zone/unit names (0-100)."""

    confidence: Literal["high", "medium", "low"]
    """Confidence level based on score.

    'high' (>80), 'medium' (50-80), 'low' (<50).
    """


class RmsCoordinateSystemMatch(BaseResponseModel):
    """A matched coordinate system."""

    rms_crs_sys: RmsCoordinateSystem
    """The source coordinate system to be matched."""

    smda_crs_sys: CoordinateSystem
    """The matched target coordinate system."""

    score: float = Field(ge=0, le=100)
    """Similarity score for the coordinate systems (0-100)."""

    confidence: Literal["high", "medium", "low"]
    """Confidence level based on score.

    'high' (>80), 'medium' (50-80), 'low' (<50).
    """
