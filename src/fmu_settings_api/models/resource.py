"""Response models for resources in .fmu."""

from typing import Any

from fmu_settings_api.models.common import BaseResponseModel


class CacheList(BaseResponseModel):
    """List of cache revision filenames."""

    revisions: list[str]
    """Cache revision filenames, sorted oldest to newest."""


class CacheContent(BaseResponseModel):
    """Content of a cache revision."""

    data: dict[str, Any]
    """Parsed JSON object for the cached resource."""
