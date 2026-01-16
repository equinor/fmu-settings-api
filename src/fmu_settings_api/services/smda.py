"""Service for querying and translating results from SMDA."""

import asyncio
from collections.abc import Sequence

from fmu.datamodels.common.masterdata import (
    CoordinateSystem,
    CountryItem,
    DiscoveryItem,
    FieldItem,
    StratigraphicColumn,
)

from fmu_settings_api.interfaces import SmdaAPI
from fmu_settings_api.models.smda import (
    SmdaField,
    SmdaFieldSearchResult,
    SmdaMasterdataResult,
    SmdaStratigraphicUnitsResult,
    StratigraphicUnit,
)


class SmdaService:
    """Service for querying SMDA API and handling business logic."""

    def __init__(self, smda_api: SmdaAPI) -> None:
        """Initialize the service with an SMDA API instance."""
        self._smda = smda_api

    async def check_health(self) -> bool:
        """Checks whether or not the current session is capable of querying SMDA."""
        await self._smda.health()
        return True

    async def search_field(self, field: SmdaField) -> SmdaFieldSearchResult:
        """Search for a field identifier in SMDA."""
        res = await self._smda.field([field.identifier])
        data = res.json()["data"]
        return SmdaFieldSearchResult(**data)

    async def get_masterdata(
        self, smda_fields: list[SmdaField]
    ) -> SmdaMasterdataResult:
        """Retrieve masterdata for fields to be confirmed in the GUI."""
        if not smda_fields:
            raise ValueError("At least one SMDA field must be provided")

        # Sorted for tests as sets don't guarantee order
        unique_field_identifiers = sorted({field.identifier for field in smda_fields})

        # Query initial list of fields (with duplicates removed)
        field_res = await self._smda.field(
            unique_field_identifiers,
            columns=[
                "country_identifier",
                "identifier",
                "projected_coordinate_system",
                "uuid",
            ],
        )
        field_results = field_res.json()["data"]["results"]
        if not field_results:
            raise ValueError(
                f"No fields found for identifiers: {unique_field_identifiers}"
            )

        field_items = [FieldItem.model_validate(field) for field in field_results]
        field_identifiers = [field.identifier for field in field_items]
        country_identifiers = list(
            {field["country_identifier"] for field in field_results}
        )

        async with asyncio.TaskGroup() as tg:
            coordinate_systems_task = tg.create_task(self._get_coordinate_systems())
            country_task = tg.create_task(self._get_countries(country_identifiers))
            discovery_task = tg.create_task(self._get_discoveries(field_identifiers))
            strat_column_task = tg.create_task(
                self._get_strat_column_areas(field_identifiers)
            )

        country_items = country_task.result()
        discovery_items = discovery_task.result()
        strat_column_items = strat_column_task.result()
        coordinate_systems = coordinate_systems_task.result()

        # Collect all field-specific coordinate systems in order
        # Track seen CRS identifiers to avoid duplicates
        field_crs_list: list[CoordinateSystem] = []
        seen_field_crs_ids: set[str] = set()
        crs_dict = {crs.identifier: crs for crs in coordinate_systems}

        for field in field_results:
            crs_id = field["projected_coordinate_system"]

            if crs_id in seen_field_crs_ids:
                continue

            field_crs = crs_dict.get(crs_id)
            if field_crs is None:
                field_id = field["identifier"]
                raise ValueError(
                    f"Coordinate system '{crs_id}' referenced by field "
                    f"'{field_id}' not found in SMDA."
                )

            field_crs_list.append(field_crs)
            seen_field_crs_ids.add(crs_id)

        field_coordinate_system = field_crs_list[0]

        remaining_crs = [
            crs
            for crs in coordinate_systems
            if crs.identifier not in seen_field_crs_ids
        ]
        field_crs_list.extend(remaining_crs)

        return SmdaMasterdataResult(
            field=field_items,
            country=country_items,
            discovery=discovery_items,
            stratigraphic_columns=strat_column_items,
            field_coordinate_system=field_coordinate_system,
            coordinate_systems=field_crs_list,
        )

    async def get_stratigraphic_units(
        self, strat_column_identifier: str
    ) -> SmdaStratigraphicUnitsResult:
        """Queries stratigraphic units for a stratigraphic column identifier."""
        if not strat_column_identifier:
            raise ValueError("A stratigraphic column identifier must be provided")

        strat_unit_res = await self._smda.strat_units(
            strat_column_identifier,
            [
                "identifier",
                "uuid",
                "strat_unit_type",
                "strat_unit_level",
                "top",
                "base",
                "top_age",
                "base_age",
                "strat_unit_parent",
                "strat_column_type",
                "color_html",
                "color_r",
                "color_g",
                "color_b",
            ],
        )
        strat_unit_results = strat_unit_res.json()["data"]["results"]

        if not strat_unit_results:
            raise ValueError(
                f"No stratigraphic units found for identifier: "
                f"{strat_column_identifier}"
            )

        strat_unit_items = []
        for strat_unit_data in strat_unit_results:
            strat_unit_item = StratigraphicUnit.model_validate(strat_unit_data)
            if strat_unit_item not in strat_unit_items:
                strat_unit_items.append(strat_unit_item)
        return SmdaStratigraphicUnitsResult(stratigraphic_units=strat_unit_items)

    async def _get_countries(
        self, country_identifiers: Sequence[str]
    ) -> list[CountryItem]:
        """Queries the list of countries that fields are in."""
        country_res = await self._smda.country(country_identifiers)
        country_results = country_res.json()["data"]["results"]

        country_items = []
        for country_data in country_results:
            country_item = CountryItem(**country_data)
            if country_item not in country_items:
                country_items.append(country_item)
        return country_items

    async def _get_discoveries(
        self, field_identifiers: Sequence[str]
    ) -> list[DiscoveryItem]:
        """Queries the list of discoveries relevant for the given fields."""
        discovery_items = []
        discovery_res = await self._smda.discovery(
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

    async def _get_strat_column_areas(
        self, field_identifiers: Sequence[str]
    ) -> list[StratigraphicColumn]:
        """Queries stratigraphic columns relevant for the list of field identifiers."""
        strat_column_items = []
        strat_column_res = await self._smda.strat_column_areas(
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

    async def _get_coordinate_systems(
        self, crs_identifiers: Sequence[str] | None = None
    ) -> list[CoordinateSystem]:
        """Queries coordinate systems from a can-be-empty list of identifiers."""
        crs_items = []
        crs_res = await self._smda.coordinate_system(crs_identifiers)
        crs_results = crs_res.json()["data"]["results"]
        for crs_data in crs_results:
            crs_item = CoordinateSystem(**crs_data)
            if crs_item not in crs_items:
                crs_items.append(crs_item)
        return crs_items
