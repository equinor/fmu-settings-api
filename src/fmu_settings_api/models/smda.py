"""Models (schemas) for the SMDA routes."""

from typing import Literal
from uuid import UUID

from fmu.datamodels.common.masterdata import (
    CoordinateSystem,
    CountryItem,
    DiscoveryItem,
    FieldItem,
    StratigraphicColumn,
)
from pydantic import Field

from fmu_settings_api.models.common import BaseResponseModel


class SmdaField(BaseResponseModel):
    """An identifier for a field to be searched for."""

    identifier: str = Field(examples=["TROLL"])
    """A field identifier (name)."""


class SmdaStratColumn(BaseResponseModel):
    """An identifier for a stratigraphic column."""

    strat_column_identifier: str = Field(examples=["LITHO_TROLL"])
    """A stratigraphic column identifier."""


class SmdaFieldUUID(BaseResponseModel):
    """Name-UUID identifier for a field as known by SMDA."""

    identifier: str = Field(examples=["TROLL"])
    """A field identifier (name)."""

    uuid: UUID
    """The SMDA UUID identifier corresponding to the field identifier."""


class SmdaFieldSearchResult(BaseResponseModel):
    """The search result of a field identifier result."""

    hits: int
    """The number of hits from the field search."""
    pages: int
    """The number of pages of hits."""
    results: list[SmdaFieldUUID]
    """A list of field identifier results from the search."""


class SmdaMasterdataResult(BaseResponseModel):
    """Contains SMDA-related attributes."""

    field: list[FieldItem]
    """A list referring to fields known to SMDA. First item is primary."""

    country: list[CountryItem]
    """A list referring to countries known to SMDA. First item is primary."""

    discovery: list[DiscoveryItem]
    """A list referring to discoveries known to SMDA. First item is primary."""

    stratigraphic_columns: list[StratigraphicColumn]
    """Reference to stratigraphic column known to SMDA."""

    field_coordinate_system: CoordinateSystem
    """The primary field's coordinate system.

    This coordinate system may not be the coordinate system users use in their model."""

    coordinate_systems: list[CoordinateSystem]
    """A list of all coordinate systems known to SMDA.

    These are provided when the user needs to select a different coordinate system that
    applies to the model they are working on."""


class StratigraphicUnit(BaseResponseModel):
    """Stratigraphic unit item."""

    identifier: str = Field(examples=["VIKING GP."])
    """The stratigraphic unit identifier (name)."""

    uuid: UUID
    """The SMDA UUID identifier corresponding to the stratigraphic unit."""

    strat_unit_type: str = Field(examples=["formation", "group"])
    """The type of stratigraphic unit."""

    strat_unit_level: int = Field(ge=1, le=6)
    """The hierarchical level of the stratigraphic unit (1-6)."""

    top: str = Field(examples=["VIKING GP. Top"])
    """The identifier (name) of the stratigraphic unit top pick (horizon)."""

    base: str = Field(examples=["VIKING GP. Base"])
    """The identifier (name) of the stratigraphic unit base pick (horizon)."""

    top_age: float = Field(ge=0, allow_inf_nan=False)
    """The age (in Ma) at the top of the stratigraphic unit."""

    base_age: float = Field(ge=0, allow_inf_nan=False)
    """The age (in Ma) at the base of the stratigraphic unit."""

    strat_unit_parent: str | None
    """The parent stratigraphic unit identifier, if applicable."""

    strat_column_type: Literal[
        "lithostratigraphy",
        "sequence stratigraphy",
        "chronostratigraphy",
        "biostratigraphy",
    ]
    """The type of stratigraphic column this unit belongs to."""

    color_html: str | None = Field(default=None, pattern="#[0-9a-fA-F]{6}")
    """The HTML hex color code for visualization."""

    color_r: int | None
    """The red component of the RGB color."""

    color_g: int | None
    """The green component of the RGB color."""

    color_b: int | None
    """The blue component of the RGB color."""


class SmdaStratigraphicUnitsResult(BaseResponseModel):
    """Result containing a list of stratigraphic units."""

    stratigraphic_units: list[StratigraphicUnit]
    """List of stratigraphic units from SMDA."""
