"""Common response models from the API."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, SecretStr


class BaseResponseModel(BaseModel):
    """Base class for all response models with attribute docstrings enabled."""

    model_config = ConfigDict(use_attribute_docstrings=True)


class Ok(BaseResponseModel):
    """Returns "ok" if the route is functioning correctly."""

    status: Literal["ok"] = "ok"


class Message(BaseResponseModel):
    """A generic message to return to the GUI."""

    message: str


class APIKey(BaseResponseModel):
    """A key-value pair for a known and supported API."""

    id: str
    key: SecretStr


class AccessToken(BaseResponseModel):
    """A key-value pair for a known and supported access scope."""

    id: str
    key: SecretStr
