"""Models (schemas) for the SMDA routes."""

from typing import Annotated, Literal
from uuid import UUID

from fmu.datamodels.fmu_results.fields import (
    CoordinateSystem,
    CountryItem,
    DiscoveryItem,
    FieldItem,
    StratigraphicColumn,
)
from pydantic import Field

from fmu_settings_api.models.common import BaseResponseModel

# Pydantic custom types
UuidStr = Annotated[
    str,
    Field(pattern="[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"),
]
StratLevelInt = Annotated[int, Field(ge=1, le=6)]
NonNanNonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class SmdaField(BaseResponseModel):
    """An identifier for a field to be searched for."""

    identifier: str = Field(examples=["TROLL"])
    """A field identifier (name)."""


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

    identifier: str
    """The stratigraphic unit identifier."""

    uuid: UUID
    """The SMDA UUID identifier corresponding to the stratigraphic unit."""

    strat_unit_type: str
    strat_unit_level: StratLevelInt
    top_age: NonNanNonNegativeFloat
    base_age: NonNanNonNegativeFloat
    strat_unit_parent: str | None
    strat_column_type: Annotated[
        str,
        (
            Literal["lithostratigraphy"]
            | Literal["sequence stratigraphy"]
            | Literal["chronostratigraphy"]
            | Literal["biostratigraphy"]
        ),
    ]
    color_html: Annotated[str, Field(pattern="#[0-9a-fA-F]{6}")] | None
    color_r: int | None
    color_g: int | None
    color_b: int | None


class SmdaStratigraphicUnitsResult(BaseResponseModel):
    """Result containing a list of stratigraphic units."""

    stratigraphic_units: list[StratigraphicUnit]
    """List of stratigraphic units from SMDA."""
