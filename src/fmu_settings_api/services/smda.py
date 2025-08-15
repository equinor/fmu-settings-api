"""Functions for querying and translating results from SMDA."""

from collections.abc import Sequence

from fmu.datamodels.fmu_results.fields import (
    CoordinateSystem,
    CountryItem,
    DiscoveryItem,
    StratigraphicColumn,
)

from fmu_settings_api.interfaces import SmdaAPI


async def get_countries(
    smda: SmdaAPI, country_identifiers: Sequence[str]
) -> list[CountryItem]:
    """Queries the list of countries the list of fields are in."""
    country_res = await smda.country(country_identifiers)
    country_results = country_res.json()["data"]["results"]

    country_items = []
    for country_data in country_results:
        country_item = CountryItem(**country_data)
        if country_item not in country_items:
            country_items.append(country_item)
    return country_items


async def get_discoveries(
    smda: SmdaAPI, field_identifiers: Sequence[str]
) -> list[DiscoveryItem]:
    """Queries the list of discoveries relevant for the given fields."""
    discovery_items = []
    discovery_res = await smda.discovery(
        field_identifiers,
        columns=[
            "field_identifier",
            "identifier",
            "short_identifier",
            "projected_coordinate_system",
            "uuid",
        ],
    )
    discovery_results = discovery_res.json()["data"]["results"]
    for discovery_data in discovery_results:
        # Skip discoveries without a short identifier
        if not discovery_data["short_identifier"]:
            continue
        discovery_item = DiscoveryItem(**discovery_data)
        if discovery_item not in discovery_items:
            discovery_items.append(discovery_item)
    return discovery_items


async def get_strat_column_areas(
    smda: SmdaAPI, field_identifiers: Sequence[str]
) -> list[StratigraphicColumn]:
    """Queries stratigraphic columns relevent for the list of field identifiers."""
    strat_column_items = []
    strat_column_res = await smda.strat_column_areas(
        field_identifiers,
        [
            "identifier",
            "uuid",
            "strat_area_identifier",
            "strat_column_identifier",
            "strat_column_status",
            "strat_column_uuid",
        ],
    )
    strat_column_results = strat_column_res.json()["data"]["results"]
    for strat_column_data in strat_column_results:
        strat_column_item = StratigraphicColumn(
            identifier=strat_column_data["strat_column_identifier"],
            uuid=strat_column_data["strat_column_uuid"],
        )
        if strat_column_item not in strat_column_items:
            strat_column_items.append(strat_column_item)
    return strat_column_items


async def get_coordinate_systems(
    smda: SmdaAPI, crs_identifiers: Sequence[str] | None = None
) -> list[CoordinateSystem]:
    """Queries coordinate systems from a can-be-empty list of identifiers."""
    crs_items = []
    crs_res = await smda.coordinate_system(crs_identifiers)
    crs_results = crs_res.json()["data"]["results"]
    for crs_data in crs_results:
        crs_item = CoordinateSystem(**crs_data)
        if crs_item not in crs_items:
            crs_items.append(crs_item)
    return crs_items
