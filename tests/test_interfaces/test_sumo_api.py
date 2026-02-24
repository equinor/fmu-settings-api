"""Test Sumo Api interface."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from fmu_settings_api.interfaces.sumo_api import SumoApi
from fmu_settings_api.models.project import SumoAsset


@pytest.fixture
def sumo_assets() -> list[SumoAsset]:
    """List of Sumo assets."""
    return [
        SumoAsset(name="TestAsset", code="001", roleprefix="ASSET1"),
        SumoAsset(name="TestAsset2", code="002", roleprefix="ASSET2"),
        SumoAsset(name="TestAsset3", code="003", roleprefix="ASSET3"),
    ]


def test_sumo_api_get_assets(
    sumo_assets: list[SumoAsset],
) -> None:
    """Tests that sumo assets are returned as expected."""
    api = SumoApi()

    with patch.object(
        api,
        "_read_assets_from_file",
        return_value=sumo_assets,
    ) as mocked_method:
        assets = api.get_assets()

        mocked_method.assert_called_once_with(api._asset_filepath)
        assert len(assets) == len(sumo_assets)
        assert assets == sumo_assets


def test_sumo_api_read_assets_from_file(
    sumo_assets: list[SumoAsset],
    tmp_path: Path,
) -> None:
    """Tests that sumo assets are read from file at the expected path."""
    file_path = tmp_path / "sumo_assets.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump([asset.model_dump() for asset in sumo_assets], f, indent=2)

    api = SumoApi()
    assets = api._read_assets_from_file(file_path)

    assert len(assets) == len(sumo_assets)
    assert assets == sumo_assets


def test_sumo_api_read_assets_from_file_raises_validation_error(
    tmp_path: Path,
) -> None:
    """Tests that invalid Sumo assets in file raises ValidationError."""
    file_path = tmp_path / "sumo_assets.json"
    invalid_model = {"name": "invalid_model"}
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump([invalid_model], f, indent=2)

    api = SumoApi()
    with pytest.raises(ValidationError):
        api._read_assets_from_file(file_path)


def test_sumo_api_read_assets_from_file_raises_json_error(tmp_path: Path) -> None:
    """Tests that non-json file content raises JSONDecodeError."""
    file_path = tmp_path / "sumo_assets.json"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("Some string that is not a valid json")

    api = SumoApi()
    with pytest.raises(json.JSONDecodeError):
        api._read_assets_from_file(file_path)


def test_sumo_api_read_assets_from_file_raises_file_not_found(tmp_path: Path) -> None:
    """Tests that FileNotFoundError is raised when file to read does not exist."""
    file_path = tmp_path / "sumo_assets.json"
    api = SumoApi()
    with pytest.raises(FileNotFoundError):
        api._read_assets_from_file(file_path)


def test_sumo_assets_json_file() -> None:
    """Tests that the sumo_assets.json file is according to rules.

    This test is here to catch if the sumo_assets.json
    file is updated wrongly and not according to the rules.
    """
    api = SumoApi()
    assets = api.get_assets()

    # Check uniquness of name among Sumo assets
    names_list = [asset.name for asset in assets]
    assert len(names_list) == len(set(names_list))

    # Check uniquness of code among Sumo assets
    codes_list = [asset.code for asset in assets]
    assert len(codes_list) == len(set(codes_list))

    # Check uniquness of roleprefix among Sumo assets
    roleprefix_list = [asset.roleprefix for asset in assets]
    assert len(roleprefix_list) == len(set(roleprefix_list))

    # Check that code can be parsed as int and is always increased by one
    last_code = 0
    for asset in assets:
        code_as_int = int(asset.code)
        assert code_as_int == last_code + 1
        last_code = code_as_int

    # Check that roleprefix relates to name
    for asset in assets:
        roleprefix = asset.roleprefix
        roleprefix_parts = roleprefix.split("-")
        asset_name = (
            asset.name.casefold().replace("æ", "e").replace("ø", "o").replace("å", "a")
        )
        assert all(part.casefold() in asset_name for part in roleprefix_parts)
