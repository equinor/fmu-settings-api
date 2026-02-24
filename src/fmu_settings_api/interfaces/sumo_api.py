"""Interface for querying Sumo's API."""

import json
from pathlib import Path
from typing import Final, Self

from pydantic import TypeAdapter

from fmu_settings_api.models.project import SumoAsset


class SumoApi:
    """Class for interacting with Sumos API."""

    def __init__(self: Self) -> None:
        """Initializes the SumoApi interface."""
        self._asset_filepath: Final[Path] = Path(__file__).parent / Path(
            "sumo_assets.json"
        )

    def get_assets(self: Self) -> list[SumoAsset]:
        """Gets the Sumo assets."""
        return self._read_assets_from_file(self._asset_filepath)

    @staticmethod
    def _read_assets_from_file(filepath: Path) -> list[SumoAsset]:
        """Reads the valid Sumo assets from file.

        The file serves as a temporary alternative to the Sumo endpoint, until
        we set up the intergration towards Sumo. The file is maintained and kept in
        sync with the assets that are onboarded to Sumo.

        Raises:
            ValidationError: If Sumo assets read from file are not valid.
            JSONDecodeError: If json file to read is not a valid json.
            FileNotFoundError: If the file to read is not found.
        """
        with open(filepath, encoding="utf-8") as stream:
            sumo_assets = json.load(stream)
        return TypeAdapter(list[SumoAsset]).validate_python(sumo_assets)
