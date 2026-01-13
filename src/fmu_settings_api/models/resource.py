"""Resource models for cache and logs."""

from enum import StrEnum
from typing import Any

from fmu_settings_api.models.common import BaseResponseModel


class CacheResource(StrEnum):
    """Available cacheable resources in the FMU project."""

    config = "config.json"


class CacheList(BaseResponseModel):
    """List of cache revision filenames."""

    revisions: list[str]
    """Cache revision filenames, sorted oldest to newest."""


class CacheContent(BaseResponseModel):
    """Content of a cache revision."""

    content: dict[str, Any]
    """Parsed JSON content from the cached file."""
