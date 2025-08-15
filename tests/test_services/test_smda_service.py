"""Tests the SMDA service functions."""

from functools import cache
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fmu.datamodels.fmu_results.fields import (
    CoordinateSystem,
    CountryItem,
    DiscoveryItem,
    StratigraphicColumn,
)

from fmu_settings_api.services.smda import (
    get_coordinate_systems,
    get_countries,
    get_discoveries,
    get_strat_column_areas,
)


@cache
def gen_uuid(identifier: str) -> UUID:
    """Generates and caches a uuid per string."""
    return uuid4()


@pytest.mark.parametrize(
    "given, mock_val",
    [
        (["Norway"], [CountryItem(identifier="Norway", uuid=gen_uuid("Norway"))]),
        (
            ["Norway", "Norway"],
            [
                CountryItem(identifier="Norway", uuid=gen_uuid("Norway")),
                CountryItem(identifier="Norway", uuid=gen_uuid("Norway")),
            ],
        ),
        (
            ["Norway", "Brazil"],
            [
                CountryItem(identifier="Norway", uuid=gen_uuid("Norway")),
                CountryItem(identifier="Brazil", uuid=gen_uuid("Brazil")),
            ],
        ),
    ],
)
async def test_get_countries(given: list[str], mock_val: list[CountryItem]) -> None:
    """Tests get_countries functions as expected."""
    mock_smda = AsyncMock()
    country_resp = MagicMock()
    country_resp.json.return_value = {
        "data": {"results": [item.model_dump() for item in mock_val]}
    }
    mock_smda.country.return_value = country_resp

    res = await get_countries(mock_smda, given)

    mock_smda.country.assert_called_with(given)
    # Check duplicated countries are pruned
    if len(set(given)) < len(given):
        assert [mock_val[0]] == res
    else:
        assert res == mock_val


@pytest.mark.parametrize(
    "given, mock_val",
    [
        (
            ["Drogon"],
            [DiscoveryItem(short_identifier="Drogon West", uuid=gen_uuid("Drogon"))],
        ),
        (
            ["Drogon", "Drogon"],
            [
                DiscoveryItem(short_identifier="Drogon West", uuid=gen_uuid("Drogon")),
                DiscoveryItem(short_identifier="Drogon East", uuid=gen_uuid("Drogon")),
            ],
        ),
        (
            ["Drogon", "Viserion"],
            [
                DiscoveryItem(short_identifier="Drogon West", uuid=gen_uuid("Drogon")),
                DiscoveryItem(short_identifier="Viserion", uuid=gen_uuid("Viserion")),
            ],
        ),
    ],
)
async def test_get_discoveries(given: list[str], mock_val: list[DiscoveryItem]) -> None:
    """Tests get_discoveries functions as expected..

    If a second discovery is present its short identifier is set to None such that is
    will not be present in the returned results.
    """
    mock_smda = AsyncMock()
    discovery_resp = MagicMock()
    results = [
        item.model_dump()
        | {
            "identifier": "Drogon West",
            "field_identifier": given[i],
            "short_identifier": None if i == 1 else item.short_identifier,
            "projected_coordinate_system": "system",
        }
        for i, item in enumerate(mock_val)
    ]
    discovery_resp.json.return_value = {"data": {"results": results}}
    mock_smda.discovery.return_value = discovery_resp

    res = await get_discoveries(mock_smda, given)

    mock_smda.discovery.assert_called_with(
        given,
        columns=[
            "field_identifier",
            "identifier",
            "short_identifier",
            "projected_coordinate_system",
            "uuid",
        ],
    )
    # Check duplicated  are pruned
    if len(given) > 1:
        assert res == [mock_val[0]]
    else:
        assert res == mock_val


@pytest.mark.parametrize(
    "given, mock_val",
    [
        (
            ["Drogon"],
            [
                StratigraphicColumn(
                    identifier="LITHO_DROGON", uuid=gen_uuid("LITHO_DROGON")
                )
            ],
        ),
        (
            ["Drogon", "Drogon"],
            [
                StratigraphicColumn(
                    identifier="LITHO_DROGON", uuid=gen_uuid("LITHO_DROGON")
                ),
                StratigraphicColumn(
                    identifier="LITHO_DROGON", uuid=gen_uuid("LITHO_DROGON")
                ),
            ],
        ),
        (
            ["Drogon", "Viserion"],
            [
                StratigraphicColumn(
                    identifier="LITHO_DROGON", uuid=gen_uuid("LITHO_DROGON")
                ),
                StratigraphicColumn(
                    identifier="LITHO_VISERION", uuid=gen_uuid("LITHO_DROGON")
                ),
            ],
        ),
    ],
)
async def test_get_strat_column_areas(
    given: list[str], mock_val: list[StratigraphicColumn]
) -> None:
    """Tests get_strat_column_areas functions as expected."""
    mock_smda = AsyncMock()
    strat_col_resp = MagicMock()
    results = [
        item.model_dump()
        | {
            "strat_area_identifier": given[i],  # The field name
            "strat_column_identifier": item.identifier,
            "strat_column_status": "official",
            "strat_column_uuid": item.uuid,
        }
        for i, item in enumerate(mock_val)
    ]
    strat_col_resp.json.return_value = {"data": {"results": results}}
    mock_smda.strat_column_areas.return_value = strat_col_resp

    res = await get_strat_column_areas(mock_smda, given)

    mock_smda.strat_column_areas.assert_called_with(
        given,
        [
            "identifier",
            "uuid",
            "strat_area_identifier",
            "strat_column_identifier",
            "strat_column_status",
            "strat_column_uuid",
        ],
    )
    # Check duplicated strat columns are pruned
    if len(set(given)) < len(given):
        assert [mock_val[0]] == res
    else:
        assert res == mock_val


@pytest.mark.parametrize(
    "given, mock_val",
    [
        (
            None,
            [
                CoordinateSystem(
                    identifier="ST_WGS84_UTM37N_P32637",
                    uuid=gen_uuid("ST_WGS84_UTM37N_P32637"),
                ),
                CoordinateSystem(
                    identifier="ST_WGS84_UTM37N_P32637",
                    uuid=gen_uuid("ST_WGS84_UTM37N_P32637"),
                ),
            ],
        ),
        (
            ["ST_WGS84_UTM37N_P32637", "ST_WGS84_UTM37N_P32637"],
            [
                CoordinateSystem(
                    identifier="ST_WGS84_UTM37N_P32637",
                    uuid=gen_uuid("ST_WGS84_UTM37N_P32637"),
                ),
                CoordinateSystem(
                    identifier="ST_WGS84_UTM37N_P32637",
                    uuid=gen_uuid("ST_WGS84_UTM37N_P32637"),
                ),
            ],
        ),
        (
            ["ST_WGS84_UTM37N_P32637", "ST_WGS84_UTM37N_P32638"],  # Last char different
            [
                CoordinateSystem(
                    identifier="ST_WGS84_UTM37N_P32637",
                    uuid=gen_uuid("ST_WGS84_UTM37N_P32637"),
                ),
                CoordinateSystem(
                    identifier="ST_WGS84_UTM37N_P32638",
                    uuid=gen_uuid("ST_WGS84_UTM37N_P32638"),
                ),
            ],
        ),
    ],
)
async def test_get_coordinate_systems(
    given: list[str], mock_val: list[CoordinateSystem]
) -> None:
    """Tests get_coordinate_systems functions as expected."""
    mock_smda = AsyncMock()
    coord_resp = MagicMock()
    coord_resp.json.return_value = {
        "data": {"results": [item.model_dump() for item in mock_val]}
    }
    mock_smda.coordinate_system.return_value = coord_resp

    res = await get_coordinate_systems(mock_smda, given)

    mock_smda.coordinate_system.assert_called_with(given)
    # Check duplicated countries are pruned
    if given is None or len(set(given)) < len(given):
        assert [mock_val[0]] == res
    else:
        assert res == mock_val
