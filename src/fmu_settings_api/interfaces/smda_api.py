"""Interface for querying SMDA's API."""

from typing import Any, Final

import httpx


class SmdaRoutes:
    """Contains routes used by routes in this API."""

    BASE_URL: Final[str] = "https://api.gateway.equinor.com/smda/v2.0"
    HEALTH: Final[str] = "actuator/health"
    FIELD_SEARCH: Final[str] = "smda-api/fields/search"


class SmdaAPI:
    """Class for interacting with SMDA's API."""

    def __init__(self, access_token: str, subscription_key: str):
        """Both token and key are required."""
        self._access_token = access_token
        self._subscription_key = subscription_key
        self._headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self._access_token}",
            "Ocp-Apim-Subscription-Key": self._subscription_key,
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

    async def field(self, field_identifier: str) -> httpx.Response:
        """Searches for a field identifier in SMDA."""
        return await self.post(
            SmdaRoutes.FIELD_SEARCH,
            json={"_projection": "identifier,uuid", "identifier": field_identifier},
        )
