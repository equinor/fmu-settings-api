"""Common response models from the API."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, SecretStr
from pydantic_core import ErrorDetails


class BaseResponseModel(BaseModel):
    """Base class for all response models with attribute docstrings enabled."""

    model_config = ConfigDict(use_attribute_docstrings=True)


class Ok(BaseResponseModel):
    """Returns "ok" if the route is functioning correctly."""

    status: Literal["ok"] = "ok"


class HealthResponse(Ok):
    """Identify a responsive FMU Settings API."""

    application: Literal["fmu-settings"] = "fmu-settings"


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
    validation_errors: list[ErrorDetails]
    """List of validation errors from Pydantic."""


class ConfigurationErrorDetail(BaseResponseModel):
    """Details for configuration errors returned in HTTP exceptions."""

    message: str
    """Error message describing the configuration issue."""
    error: str
    """Additional error details or context."""


class MigrationErrorResponse(BaseResponseModel):
    """Migration error response with a string detail and a specific error code."""

    code: Literal["newer_schema_version"]
    """Machine-readable error code."""
    detail: str
    """Error message describing the migration failure."""
