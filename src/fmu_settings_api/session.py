"""Functionality for managing sessions."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Self
from uuid import uuid4

from fmu.settings import FMUDirectory

from fmu_settings_api.config import settings


@dataclass
class Session:
    """Represents session information when working on an FMU Directory."""

    id: str
    fmu_directory: FMUDirectory
    created_at: datetime
    expires_at: datetime
    last_accessed: datetime


class SessionManager:
    """Manages sessions started when an FMU Directory as been opened.

    A better implementation would involve creating a storage backend interface that all
    backends implement. Because our use case is simple only hints of this are here and
    it simply uses a dictionary backend.
    """

    Storage = dict[str, Session]
    """Type alias for the storage backend instance."""

    storage: Storage
    """Instances of the storage backend."""

    def __init__(self: Self) -> None:
        """Initializes the session manager singleton."""
        self.storage = {}

    async def _store_session(self: Self, session_id: str, session: Session) -> None:
        """Stores a newly created session."""
        self.storage[session_id] = session

    async def _retrieve_session(self: Self, session_id: str) -> Session | None:
        """Retrieves a session from the storage backend."""
        return self.storage.get(session_id, None)

    async def _update_session(self: Self, session_id: str, session: Session) -> None:
        """Stores an updated session back into the session backend."""
        self.storage[session_id] = session

    async def destroy_session(self: Self, session_id: str) -> None:
        """Destroys a session by its session id."""
        session = await self._retrieve_session(session_id)
        if session is not None:
            del self.storage[session_id]

    async def create_session(
        self: Self,
        fmu_directory: FMUDirectory,
        expire_seconds: int = settings.SESSION_EXPIRE_SECONDS,
    ) -> str:
        """Creates a new session and stores it to the storage backend."""
        session_id = str(uuid4())
        now = datetime.now(UTC)
        expiration_duration = timedelta(seconds=expire_seconds)

        session = Session(
            id=session_id,
            fmu_directory=fmu_directory,
            created_at=now,
            expires_at=now + expiration_duration,
            last_accessed=now,
        )
        await self._store_session(session_id, session)

        return session_id

    async def get_session(self: Self, session_id: str) -> Session | None:
        """Get the session data for a session id."""
        session = await self._retrieve_session(session_id)
        if not session:
            return None

        now = datetime.now(UTC)
        if session.expires_at < now:
            await self.destroy_session(session_id)
            return None

        session.last_accessed = now
        await self._update_session(session_id, session)
        return session


session_manager = SessionManager()


async def create_fmu_session(
    fmu_directory: FMUDirectory,
    expire_seconds: int = settings.SESSION_EXPIRE_SECONDS,
) -> str:
    """Creates a new session and stores it in the session mananger."""
    return await session_manager.create_session(fmu_directory, expire_seconds)


async def destroy_fmu_session(session_id: str) -> None:
    """Destroys a session in the session manager."""
    await session_manager.destroy_session(session_id)
