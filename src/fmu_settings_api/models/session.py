"""Response models related to session state."""

from datetime import datetime

from fmu_settings_api.models.common import BaseResponseModel


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
