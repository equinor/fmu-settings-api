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


class SmdaSelectedField(BaseResponseModel):
    """A selected field for masterdata lookup."""

    identifier: str = Field(examples=["TROLL"])
    """A field identifier (name)."""

    uuid: UUID | None = None
    """The SMDA UUID identifier corresponding to the field identifier."""


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

    country: str
    """The country identifier corresponding to the field identifier."""


class SmdaFieldSearchResult(BaseResponseModel):
    """The search result of a field identifier result."""

    hits: int
    """The number of hits from the field search."""
    pages: int
    """The number of pages of hits."""
    results: list[SmdaFieldUUID]
    """A list of field identifier results from the search."""


class SmdaWellHeader(BaseResponseModel):
    """Well header data from SMDA."""

    unique_well_identifier: str
    """Unique SMDA identifier for the well."""

    unique_wellbore_identifier: str
    """Unique SMDA identifier for the wellbore."""

    official_wellbore_name: str | None
    """Official wellbore name used by the Authorities.

    For Norway and UK, it will be the unique_wellbore_identifier without
    country iso code, but for Brazil it can really differs from the Equinor
    wellbore name.
    """

    country_identifier: str
    """Country identifier for the wellbore."""

    parent_wellbore: str | None
    """The unique wellbore identifier this wellbore is kicked off from.

    Ref. kick off depth. This is used for sidetracks. A wellbore starting at
    the well origin has no parent.
    """

    wellbore_type: str | None
    """Type of wellbore, values like exploration, development, other.

    This attribute is automatically maintained in SMDA based on the wellbore
    purpose. If the purpose is like wildcat or appraisal, type will be set to
    exploration, if the purpose is like production, injection then the type is
    set to development.
    """

    wellbore_purpose: str | None
    """Purpose of wellbore.

    Values like wildcat, appraisal, … for exploration wellbores; production,
    injection, observation, disposal, … for development wellbores; shallow gas,
    pilot hole for other purpose.
    """

    wellbore_status: str | None
    """Status of the wellbore.

    Value like plugged and abandoned, drilling, plugged, producing ... This
    attribute is automatically maintained in SMDA if no good source is found
    for it. SMDA will use the wellbore type (exploration or development), the
    drill dates information, current_track, etc ... in order to set a plausible
    status. If wellbore type=exploration and completed_date < current_date,
    then status=plugged and abandoned while development wellbore would be set
    to completed.
    """

    wellbore_purpose_planned: str | None
    """Pre-drill purpose of the wellbore.

    Legal values for exploration wellbores: wildcat, appraisal. Example of
    legal values for development wellbores: observation, production, injection.
    """

    drill_year: int | None
    """The year when the drilling has started."""

    completion_date: str | None
    """Date when the wellbore is considered completed.

    For exploration wellbores from moveable facilities, this may be the anchor
    handling or jacking-down start date. For fixed facilities and development
    wellbores, it is when the wellbore reaches total depth and the last casing,
    liner, or screen is set. If immediately plugged, it is the date the last
    plug is set.
    """

    discovery_internal_identifier: str | None
    """Internal name of the discovery."""

    multilateral: Literal[0, 1] | None
    """Whether the wellbore is multilateral. 0 = no, 1 = yes."""

    projected_coordinate_unit: str | None
    """Projected coordinate unit."""

    projected_coordinate_system: str | None
    """Coordinate reference system for the easting/northing values."""

    well_uuid: UUID
    """SMDA UUID for the well."""

    wellbore_uuid: UUID
    """SMDA UUID for the wellbore."""


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

    top_uuid: UUID | None
    """The SMDA UUID identifier corresponding to the top horizon."""

    base: str = Field(examples=["VIKING GP. Base"])
    """The identifier (name) of the stratigraphic unit base pick (horizon)."""

    base_uuid: UUID | None
    """The SMDA UUID identifier corresponding to the base horizon."""

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


class SmdaWellHeadersResult(BaseResponseModel):
    """Result containing a list of well headers."""

    well_headers: list[SmdaWellHeader]
    """List of well headers from SMDA."""
