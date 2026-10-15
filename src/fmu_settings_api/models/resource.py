"""Response models for resources in .fmu."""

from typing import Any

from pydantic import AwareDatetime

from fmu_settings_api.models.common import BaseResponseModel


class CacheList(BaseResponseModel):
    """List of cache revision filenames."""

    revisions: list[str]
    """Cache revision filenames, sorted oldest to newest."""


class CacheContent(BaseResponseModel):
    """Content of a cache revision."""

    data: dict[str, Any]
    """Parsed JSON object for the cached resource."""


class MigrationBackupStatus(BaseResponseModel):
    """Availability of a restorable project config migration backup."""

    available: bool
    """Whether a backup compatible with the installed schema exists."""
    last_modified_at: AwareDatetime | None = None
    """When the config in the backup was last modified."""
    last_modified_by: str | None = None
    """Who last modified the config in the backup."""
