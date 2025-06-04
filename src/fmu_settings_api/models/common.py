"""Common response models from the API."""

from typing import Literal

from pydantic import BaseModel, SecretStr


class Ok(BaseModel):
    """Returns "ok" if the route is functioning correctly."""

    status: Literal["ok"] = "ok"


class Message(BaseModel):
    """A generic message to return to the GUI."""

    message: str


class APIKey(BaseModel):
    """A key-value pair for a known and supported API."""

    id: str
    key: SecretStr


class AccessToken(BaseModel):
    """A key-value pair for a known and supported access scope."""

    id: str
    key: SecretStr
