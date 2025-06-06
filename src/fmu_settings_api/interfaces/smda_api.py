"""Interface for querying SMDA's API."""

from typing import Final

import requests


class SmdaRoutes:
    """Contains routes used by routes in this API."""

    BASE_URL: Final[str] = "https://api.gateway.equinor.com/smda/v2.0"
    HEALTH: Final[str] = "actuator/health"


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

    async def get(self, route: str) -> requests.Response:
        """Makes a GET request to SMDA.

        Returns:
            The requests response on success

        Raises:
            requests.exceptions.HTTPError if not 200
        """
        url = f"{SmdaRoutes.BASE_URL}/{route}"
        res = requests.get(url, headers=self._headers)
        res.raise_for_status()
        return res

    async def health(self) -> bool:
        """Checks if the access token and subscription key are valid."""
        res = await self.get(SmdaRoutes.HEALTH)
        return res.status_code == requests.codes.ok
