"""Response models related to session state."""

from datetime import datetime

from pydantic import Field

from fmu_settings_api.models.common import BaseResponseModel
from fmu_settings_api.models.project import FMUProject


class SessionResponse(BaseResponseModel):
    """Serializable representation of the current session."""

    id: str
    """Session identifier."""

    created_at: datetime
    """Timestamp when the session was created."""

    expires_at: datetime
    """Timestamp when the session will expire."""

    last_accessed: datetime
    """Timestamp when the session was last accessed."""

    project: FMUProject | None = Field(default=None)
    """Details about the opened project, if any."""

    project_lock_errors: dict[str, str | None] | None = Field(default=None)
    """Most recent lock operation errors for the opened project."""
