"""Common response models from the API."""

from pydantic import BaseModel, SecretStr


class Message(BaseModel):
    """A generic message to return to the GUI."""

    message: str


class APIKey(BaseModel):
    """A key-value pair for a known and supported API."""

    id: str
    key: SecretStr
