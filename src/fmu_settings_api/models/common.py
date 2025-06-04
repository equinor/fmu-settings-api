"""Common response models from the API."""

from typing import Literal

from fmu.settings.models.user_config import UserConfig
from pydantic import BaseModel, SecretStr

from .project import FMUProject


class HealthCheck(BaseModel):
    """Returns "ok" if the route is functioning correctly."""

    status: Literal["ok"] = "ok"


class SessionResponse(BaseModel):
    """Information returned when a session is initially created."""

    user_config: UserConfig
    fmu_project: FMUProject | None = None


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
