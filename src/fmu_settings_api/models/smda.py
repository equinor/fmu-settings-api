"""Models (schemas) for the SMDA routes."""

from uuid import UUID

from fmu.settings.models.smda import (
    CoordinateSystem,
    CountryItem,
    DiscoveryItem,
    FieldItem,
    StratigraphicColumn,
)
from pydantic import BaseModel, Field


class SmdaField(BaseModel):
    """An identifier for a field to be searched for."""

    identifier: str = Field(examples=["TROLL"])
    """A field identifier (name)."""


class SmdaFieldUUID(BaseModel):
    """Name-UUID identifier for a field as known by SMDA."""

    identifier: str = Field(examples=["TROLL"])
    """A field identifier (name)."""

    uuid: UUID
    """The SMDA UUID identifier corresponding to the field identifier."""


class SmdaFieldSearchResult(BaseModel):
    """The search result of a field identifier result."""

    hits: int
    """The number of hits from the field search."""
    pages: int
    """The number of pages of hits."""
    results: list[SmdaFieldUUID]
    """A list of field identifier results from the search."""


class SmdaMasterdataResult(BaseModel):
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
