"""Models (schemas) for the SMDA routes."""

from uuid import UUID

from pydantic import BaseModel, Field


class SMDAField(BaseModel):
    """An identifier for a field to be searched for."""

    identifier: str = Field(examples=["TROLL"])
    """A field identifier (name)."""


class SMDAFieldUUID(BaseModel):
    """Name-UUID identifier for a field as known by SMDA."""

    identifier: str = Field(examples=["TROLL"])
    """A field identifier (name)."""

    uuid: UUID
    """The SMDA UUID identifier corresponding to the field identifier."""


class SMDAFieldSearchResult(BaseModel):
    """The search result of a field identifier result."""

    hits: int
    """The number of hits from the field search."""
    pages: int
    """The number of pages of hits."""
    results: list[SMDAFieldUUID]
    """A list of field identifier results from the search."""
