"""Tests the SMDA service functions."""

from functools import cache
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import httpx
import pytest
from fmu.datamodels.common.masterdata import (
    CoordinateSystem,
    CountryItem,
    DiscoveryItem,
    StratigraphicColumn,
)

from fmu_settings_api.models.smda import SmdaField, SmdaSelectedField
from fmu_settings_api.services.smda import SmdaService


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

    service = SmdaService(mock_smda)
    res = await service._get_countries(given)

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

    service = SmdaService(mock_smda)
    res = await service._get_discoveries(given)

    mock_smda.discovery.assert_called_with(
        given,
        columns=[
            "short_identifier",
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

    service = SmdaService(mock_smda)
    res = await service._get_strat_column_areas(given)

    mock_smda.strat_column_areas.assert_called_with(
        given,
        [
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

    service = SmdaService(mock_smda)
    res = await service._get_coordinate_systems(given)

    mock_smda.coordinate_system.assert_called_with(given)
    # Check duplicated countries are pruned
    if given is None or len(set(given)) < len(given):
        assert [mock_val[0]] == res
    else:
        assert res == mock_val


async def test_get_stratigraphic_units_success() -> None:
    """Tests get_stratigraphic_units returns units correctly."""
    expected_horizon_lookup_count = 2
    mock_smda = AsyncMock()
    strat_unit_resp = MagicMock()
    top_horizon_uuid = gen_uuid("VIKING GP. Top")
    base_horizon_uuid = gen_uuid("VIKING GP. Base")
    strat_unit_resp.json.return_value = {
        "data": {
            "results": [
                {
                    "identifier": "VIKING GP.",
                    "uuid": gen_uuid("VIKING GP."),
                    "strat_unit_type": "group",
                    "strat_unit_level": 2,
                    "top": "VIKING GP. Top",
                    "base": "VIKING GP. Base",
                    "top_age": 2.58,
                    "base_age": 5.33,
                    "strat_unit_parent": None,
                    "strat_column_type": "lithostratigraphy",
                    "color_html": "#FFD700",
                    "color_r": 255,
                    "color_g": 215,
                    "color_b": 0,
                }
            ]
        }
    }
    mock_smda.strat_units.return_value = strat_unit_resp

    horizon_responses = {
        "VIKING GP. Top": {
            "data": {
                "results": [
                    {
                        "identifier": "VIKING GP. Top",
                        "uuid": str(top_horizon_uuid),
                    }
                ]
            }
        },
        "VIKING GP. Base": {
            "data": {
                "results": [
                    {
                        "identifier": "VIKING GP. Base",
                        "uuid": str(base_horizon_uuid),
                    }
                ]
            }
        },
    }

    async def horizon_side_effect(identifier: str) -> MagicMock:
        horizon_resp = MagicMock()
        horizon_resp.json.return_value = horizon_responses[identifier]
        return horizon_resp

    mock_smda.horizon.side_effect = horizon_side_effect

    service = SmdaService(mock_smda)
    result = await service.get_stratigraphic_units("LITHO_DROGON")

    mock_smda.strat_units.assert_called_with(
        "LITHO_DROGON",
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
    assert mock_smda.horizon.await_count == expected_horizon_lookup_count
    mock_smda.horizon.assert_any_await("VIKING GP. Top")
    mock_smda.horizon.assert_any_await("VIKING GP. Base")
    assert len(result.stratigraphic_units) == 1
    assert result.stratigraphic_units[0].identifier == "VIKING GP."
    assert result.stratigraphic_units[0].strat_unit_type == "group"
    assert result.stratigraphic_units[0].top_horizon_uuid == top_horizon_uuid
    assert result.stratigraphic_units[0].base_horizon_uuid == base_horizon_uuid


async def test_get_stratigraphic_units_empty_identifier() -> None:
    """Tests ValueError raised when empty identifier provided."""
    mock_smda = AsyncMock()
    service = SmdaService(mock_smda)

    with pytest.raises(ValueError, match="must be provided"):
        await service.get_stratigraphic_units("")


async def test_get_stratigraphic_units_no_results() -> None:
    """Tests ValueError raised when SMDA returns empty results."""
    mock_smda = AsyncMock()
    strat_unit_resp = MagicMock()
    strat_unit_resp.json.return_value = {"data": {"results": []}}
    mock_smda.strat_units.return_value = strat_unit_resp

    service = SmdaService(mock_smda)

    with pytest.raises(ValueError, match="No stratigraphic units found"):
        await service.get_stratigraphic_units("NONEXISTENT")


async def test_get_stratigraphic_units_deduplicates() -> None:
    """Tests duplicate stratigraphic units are filtered out."""
    mock_smda = AsyncMock()
    strat_unit_resp = MagicMock()
    top_horizon_uuid = gen_uuid("VIKING GP. Top")
    base_horizon_uuid = gen_uuid("VIKING GP. Base")
    strat_unit_resp.json.return_value = {
        "data": {
            "results": [
                {
                    "identifier": "VIKING GP.",
                    "uuid": gen_uuid("VIKING GP."),
                    "strat_unit_type": "group",
                    "strat_unit_level": 2,
                    "top": "VIKING GP. Top",
                    "base": "VIKING GP. Base",
                    "top_age": 2.58,
                    "base_age": 5.33,
                    "strat_unit_parent": None,
                    "strat_column_type": "lithostratigraphy",
                    "color_html": "#FFD700",
                    "color_r": 255,
                    "color_g": 215,
                    "color_b": 0,
                },
                {
                    "identifier": "VIKING GP.",
                    "uuid": gen_uuid("VIKING GP."),
                    "strat_unit_type": "group",
                    "strat_unit_level": 2,
                    "top": "VIKING GP. Top",
                    "base": "VIKING GP. Base",
                    "top_age": 2.58,
                    "base_age": 5.33,
                    "strat_unit_parent": None,
                    "strat_column_type": "lithostratigraphy",
                    "color_html": "#FFD700",
                    "color_r": 255,
                    "color_g": 215,
                    "color_b": 0,
                },
            ]
        }
    }
    mock_smda.strat_units.return_value = strat_unit_resp

    async def horizon_side_effect(identifier: str) -> MagicMock:
        horizon_resp = MagicMock()
        horizon_resp.json.return_value = {
            "data": {
                "results": [
                    {
                        "identifier": identifier,
                        "uuid": str(
                            top_horizon_uuid
                            if identifier == "VIKING GP. Top"
                            else base_horizon_uuid
                        ),
                    }
                ]
            }
        }
        return horizon_resp

    mock_smda.horizon.side_effect = horizon_side_effect

    service = SmdaService(mock_smda)
    result = await service.get_stratigraphic_units("LITHO_DROGON")

    assert len(result.stratigraphic_units) == 1
    assert result.stratigraphic_units[0].top_horizon_uuid == top_horizon_uuid
    assert result.stratigraphic_units[0].base_horizon_uuid == base_horizon_uuid


async def test_get_stratigraphic_units_horizon_http_error_returns_null_uuids() -> None:
    """Tests horizon lookup errors do not fail stratigraphic units response."""
    mock_smda = AsyncMock()
    strat_unit_resp = MagicMock()
    strat_unit_resp.json.return_value = {
        "data": {
            "results": [
                {
                    "identifier": "VIKING GP.",
                    "uuid": gen_uuid("VIKING GP."),
                    "strat_unit_type": "group",
                    "strat_unit_level": 2,
                    "top": "VIKING GP. Top",
                    "base": "VIKING GP. Base",
                    "top_age": 2.58,
                    "base_age": 5.33,
                    "strat_unit_parent": None,
                    "strat_column_type": "lithostratigraphy",
                    "color_html": "#FFD700",
                    "color_r": 255,
                    "color_g": 215,
                    "color_b": 0,
                }
            ]
        }
    }
    mock_smda.strat_units.return_value = strat_unit_resp

    mock_request = httpx.Request(method="POST", url="https://smda/strat-surface-names")
    mock_response = httpx.Response(status_code=503, request=mock_request)
    mock_smda.horizon.side_effect = httpx.HTTPStatusError(
        "503 Service Unavailable",
        request=mock_request,
        response=mock_response,
    )

    service = SmdaService(mock_smda)
    result = await service.get_stratigraphic_units("LITHO_DROGON")

    assert len(result.stratigraphic_units) == 1
    assert result.stratigraphic_units[0].top_horizon_uuid is None
    assert result.stratigraphic_units[0].base_horizon_uuid is None


async def test_get_masterdata_no_fields_found() -> None:
    """Tests that get_masterdata raises ValueError when no fields are found."""
    mock_smda = AsyncMock()
    field_resp = MagicMock()
    field_resp.json.return_value = {"data": {"results": []}}
    mock_smda.field.return_value = field_resp

    service = SmdaService(mock_smda)

    with pytest.raises(ValueError) as exc_info:
        await service.get_masterdata([SmdaSelectedField(identifier="NONEXISTENT")])

    assert "No fields found for identifiers" in str(exc_info.value)


async def test_search_field_adds_country_to_results() -> None:
    """Tests that field search exposes country in each result row."""
    mock_smda = AsyncMock()
    field_resp = MagicMock()
    field_uuid = uuid4()
    field_resp.json.return_value = {
        "data": {
            "hits": 1,
            "pages": 1,
            "results": [
                {
                    "country_identifier": "Norway",
                    "identifier": "DROGON",
                    "uuid": field_uuid,
                }
            ],
        }
    }
    mock_smda.field.return_value = field_resp

    service = SmdaService(mock_smda)
    result = await service.search_field(SmdaField(identifier="DROGON"))

    mock_smda.field.assert_called_once_with(
        ["DROGON"],
        columns=["country_identifier", "identifier", "uuid"],
    )
    assert result.results[0].country == "Norway"


async def test_get_masterdata_uses_selected_field_uuid_for_lookup() -> None:
    """Tests that get_masterdata uses the selected field uuid for lookup."""
    mock_smda = AsyncMock()
    selected_uuid = uuid4()
    field_resp = MagicMock()
    field_resp.json.return_value = {
        "data": {
            "results": [
                {
                    "country_identifier": "Norway",
                    "identifier": "DROGON",
                    "projected_coordinate_system": "ST_WGS84_UTM37N_P32637",
                    "uuid": selected_uuid,
                },
            ]
        }
    }
    mock_smda.field.return_value = field_resp
    mock_smda.coordinate_system.return_value = MagicMock(
        json=MagicMock(
            return_value={
                "data": {
                    "results": [
                        {
                            "identifier": "ST_WGS84_UTM37N_P32637",
                            "uuid": uuid4(),
                        },
                        {
                            "identifier": "ST_WGS84_UTM37N_P32638",
                            "uuid": uuid4(),
                        },
                    ]
                }
            }
        )
    )
    mock_smda.country.return_value = MagicMock(
        json=MagicMock(
            return_value={
                "data": {
                    "results": [
                        {"identifier": "Norway", "uuid": uuid4()},
                    ]
                }
            }
        )
    )
    mock_smda.discovery.return_value = MagicMock(
        json=MagicMock(return_value={"data": {"results": []}})
    )
    mock_smda.strat_column_areas.return_value = MagicMock(
        json=MagicMock(return_value={"data": {"results": []}})
    )

    service = SmdaService(mock_smda)
    result = await service.get_masterdata(
        [SmdaSelectedField(identifier="DROGON", uuid=selected_uuid)]
    )

    mock_smda.field.assert_called_once_with(
        field_uuid=selected_uuid,
        columns=[
            "country_identifier",
            "identifier",
            "projected_coordinate_system",
            "uuid",
        ],
    )
    assert len(result.field) == 1
    assert result.field[0].uuid == selected_uuid
