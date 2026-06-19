"""Common response models from the API."""

from pathlib import Path
from typing import Any, Literal

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


class RestorableFilesResponse(BaseResponseModel):
    """A list of missing .fmu files that can be restored or were restored."""

    files: list[Path]
    """Relative paths to the restorable or restored files."""


class APIKey(BaseResponseModel):
    """A key-value pair for a known and supported API."""

    id: str
    key: SecretStr


class AccessToken(BaseResponseModel):
    """A key-value pair for a known and supported access scope."""

    id: str
    key: SecretStr


class ValidationErrorDetail(BaseResponseModel):
    """Details for validation errors returned in HTTP exceptions."""

    message: str
    """Error message describing the validation failure."""
    validation_errors: Any
    """List of validation errors from Pydantic, typically list[dict[str, Any]]."""


class ConfigurationErrorDetail(BaseResponseModel):
    """Details for configuration errors returned in HTTP exceptions."""

    message: str
    """Error message describing the configuration issue."""
    error: str
    """Additional error details or context."""
