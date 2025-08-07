"""Interface for querying SMDA's API."""

from collections.abc import Sequence
from typing import Any, Final

import httpx

from fmu_settings_api.config import HttpHeader


class SmdaRoutes:
    """Contains routes used by routes in this API."""

    BASE_URL: Final[str] = "https://api.gateway.equinor.com/smda/v2.0"
    HEALTH: Final[str] = "actuator/health"
    FIELDS_SEARCH: Final[str] = "smda-api/fields/search"
    COUNTRIES_SEARCH: Final[str] = "smda-api/countries/search"
    DISCOVERIES_SEARCH: Final[str] = "smda-api/discoveries/search"
    STRAT_COLUMN_AREAS_SEARCH: Final[str] = "smda-api/strat-column-areas/search"
    COORDINATE_SYSTEM_SEARCH: Final[str] = "smda-api/crs/search"


class SmdaAPI:
    """Class for interacting with SMDA's API."""

    def __init__(self, access_token: str, subscription_key: str):
        """Both token and key are required."""
        self._access_token = access_token
        self._subscription_key = subscription_key
        self._headers = {
            HttpHeader.CONTENT_TYPE_KEY: HttpHeader.CONTENT_TYPE_JSON,
            HttpHeader.AUTHORIZATION_KEY: f"Bearer {self._access_token}",
            HttpHeader.OCP_APIM_SUBSCRIPTION_KEY: self._subscription_key,
        }

    async def get(self, route: str) -> httpx.Response:
        """Makes a GET request to SMDA.

        Returns:
            The httpx response on success

        Raises:
            httpx.HTTPError if not 200
        """
        url = f"{SmdaRoutes.BASE_URL}/{route}"
        async with httpx.AsyncClient() as client:
            res = await client.get(url, headers=self._headers)
        res.raise_for_status()
        return res

    async def post(
        self, route: str, json: dict[str, Any] | None = None
    ) -> httpx.Response:
        """Makes a POST request to SMDA.

        Returns:
            The httpx response on success

        Raises:
            httpx.HTTPError if not 200
        """
        url = f"{SmdaRoutes.BASE_URL}/{route}"
        async with httpx.AsyncClient() as client:
            res = await client.post(url, headers=self._headers, json=json)
        res.raise_for_status()
        return res

    async def health(self) -> bool:
        """Checks if the access token and subscription key are valid."""
        res = await self.get(SmdaRoutes.HEALTH)
        return res.status_code == httpx.codes.OK

    async def field(
        self, field_identifiers: Sequence[str], columns: Sequence[str] | None = None
    ) -> httpx.Response:
        """Searches for a field identifier in SMDA."""
        _projection = "identifier,uuid" if columns is None else ",".join(columns)

        return await self.post(
            SmdaRoutes.FIELDS_SEARCH,
            json={"_projection": _projection, "identifier": field_identifiers},
        )

    async def country(
        self, country_identifiers: Sequence[str], columns: Sequence[str] | None = None
    ) -> httpx.Response:
        """Searches for a country identifier in SMDA."""
        _projection = "identifier,uuid" if columns is None else ",".join(columns)
        return await self.post(
            SmdaRoutes.COUNTRIES_SEARCH,
            json={"_projection": _projection, "identifier": country_identifiers},
        )

    async def discovery(
        self, field_identifiers: Sequence[str], columns: Sequence[str] | None = None
    ) -> httpx.Response:
        """Searches for discoveries related to a field identifier."""
        _projection = "identifier,uuid" if columns is None else ",".join(columns)
        return await self.post(
            SmdaRoutes.DISCOVERIES_SEARCH,
            json={"_projection": _projection, "field_identifier": field_identifiers},
        )

    async def strat_column_areas(
        self, field_identifiers: Sequence[str], columns: Sequence[str] | None = None
    ) -> httpx.Response:
        """Searches for the stratigraphic column related to a field identifier."""
        _projection = "identifier,uuid" if columns is None else ",".join(columns)
        return await self.post(
            SmdaRoutes.STRAT_COLUMN_AREAS_SEARCH,
            json={
                "_projection": _projection,
                "strat_area_identifier": field_identifiers,
                "strat_column_status": "official",
            },
        )

    async def coordinate_system(
        self,
        crs_identifier: Sequence[str] | None = None,
        columns: Sequence[str] | None = None,
    ) -> httpx.Response:
        """Searches for the stratigraphic column related to a field identifier."""
        _projection = "identifier,uuid" if columns is None else ",".join(columns)

        json: dict[str, Any] = {"_projection": _projection, "_items": 9999}
        if crs_identifier:
            json["identifier"] = crs_identifier

        return await self.post(SmdaRoutes.COORDINATE_SYSTEM_SEARCH, json=json)
