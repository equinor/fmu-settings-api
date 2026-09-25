"""Interface for querying Sumo's API."""

import json
from typing import Self

import httpx
from pydantic import TypeAdapter, ValidationError
from sumo.wrapper import SumoClient  # type: ignore[import-untyped]

from fmu_settings_api.models.project import SumoAsset


class SumoAuthenticationRequiredError(Exception):
    """Raised when Sumo requires an interactive user login."""


class SumoUnavailableError(Exception):
    """Raised when the Sumo API is unavailable."""


class SumoInvalidResponseError(Exception):
    """Raised when Sumo returns data with an unexpected structure."""


class SumoApi:
    """Class for interacting with Sumo's API."""

    def __init__(self: Self, environment: str = "prod") -> None:
        """Initialize the interface for a Sumo environment."""
        self._environment = environment

    def get_assets(self: Self) -> list[SumoAsset]:
        """Return the assets to which the current user has write access."""
        try:
            sumo_client = SumoClient(env=self._environment, interactive=False)
        except Exception as e:  # noqa: BLE001
            raise SumoUnavailableError("Unable to get assets from Sumo") from e

        try:
            with sumo_client as sumo:
                self._get_access_token(sumo)
                response = sumo.get("/userpermissions")
        except httpx.HTTPError as e:
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 401:
                raise SumoAuthenticationRequiredError("Sumo login is required") from e
            raise SumoUnavailableError("Unable to get assets from Sumo") from e

        try:
            assets = TypeAdapter(dict[str, list[str]]).validate_python(response.json())
        except (json.JSONDecodeError, ValidationError) as e:
            raise SumoInvalidResponseError(
                "Sumo returned an invalid asset response"
            ) from e

        return [
            SumoAsset(name=name)
            for name, permissions in sorted(assets.items())
            if "write" in permissions
        ]

    def login(self: Self) -> None:
        """Start an interactive Sumo login when no cached token is available."""
        try:
            sumo_client = SumoClient(env=self._environment, interactive=True)
        except Exception as e:  # noqa: BLE001
            raise SumoUnavailableError("Unable to connect to Sumo") from e

        try:
            with sumo_client as sumo:
                self._get_access_token(sumo)
        except httpx.HTTPError as e:
            raise SumoUnavailableError("Unable to connect to Sumo") from e

    @staticmethod
    def _get_access_token(sumo: SumoClient) -> None:
        """Get a cached, refreshed, or interactively acquired access token."""
        try:
            token = sumo.authenticate()
        except Exception as e:  # noqa: BLE001
            if str(e) == "No valid authorization provider found.":
                raise SumoAuthenticationRequiredError("Sumo login is required") from e
            raise SumoUnavailableError("Unable to authenticate with Sumo") from e

        if token is None:
            raise SumoAuthenticationRequiredError("Sumo login was not completed")
