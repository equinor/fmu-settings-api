"""Functionality for managing sessions."""

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Self
from uuid import uuid4

from fmu.settings import ProjectFMUDirectory
from fmu.settings._fmu_dir import UserFMUDirectory
from pydantic import BaseModel, SecretStr

from fmu_settings_api.config import settings
from fmu_settings_api.models.common import AccessToken
from fmu_settings_api.services.user import add_to_user_recent_projects


class SessionNotFoundError(ValueError):
    """Raised when getting a session id that does not exist."""


class AccessTokens(BaseModel):
    """Known access tokens that can be set by the GUI."""

    fmu_settings: SecretStr | None = None
    smda_api: SecretStr | None = None


class LockErrors(BaseModel):
    """Lock-related error messages tracked for a project session."""

    acquire: str | None = None
    release: str | None = None
    refresh: str | None = None


@dataclass
class Session:
    """Represents session information when working on an FMU Directory."""

    id: str
    user_fmu_directory: UserFMUDirectory
    created_at: datetime
    expires_at: datetime
    last_accessed: datetime
    access_tokens: AccessTokens


@dataclass
class ProjectSession(Session):
    """A session with an FMU project attached."""

    project_fmu_directory: ProjectFMUDirectory
    lock_errors: LockErrors = field(default_factory=LockErrors)


class SessionManager:
    """Manages sessions started when an FMU Directory has been opened.

    A better implementation would involve creating a storage backend interface that all
    backends implement. Because our use case is simple only hints of this are here and
    it simply uses a dictionary backend.
    """

    Storage = dict[str, Session | ProjectSession]
    """Type alias for the storage backend instance."""

    storage: Storage
    """Instances of the storage backend."""

    def __init__(self: Self) -> None:
        """Initializes the session manager singleton."""
        self.storage = {}

    async def _store_session(
        self: Self, session_id: str, session: Session | ProjectSession
    ) -> None:
        """Stores a newly created session."""
        self.storage[session_id] = session

    async def _retrieve_session(
        self: Self, session_id: str
    ) -> Session | ProjectSession | None:
        """Retrieves a session from the storage backend."""
        return self.storage.get(session_id, None)

    async def _update_session(
        self: Self, session_id: str, session: Session | ProjectSession
    ) -> None:
        """Stores an updated session back into the session backend."""
        self.storage[session_id] = session

    async def destroy_session(self: Self, session_id: str) -> None:
        """Destroys a session by its session id."""
        session = await self._retrieve_session(session_id)
        if session is not None:
            try:
                if isinstance(session, ProjectSession):
                    try:
                        session.project_fmu_directory._lock.release()
                    except Exception as e:
                        session.lock_errors.release = str(e)
            finally:
                del self.storage[session_id]

    async def create_session(
        self: Self,
        user_fmu_directory: UserFMUDirectory,
        expire_seconds: int = settings.SESSION_EXPIRE_SECONDS,
    ) -> str:
        """Creates a new session and stores it to the storage backend.

        Params:
            user_fmu_directory: The user .fmu directory instance
            expire_seconds: How long the session should be valid. Optional, defaulted.

        Returns:
            The session id of the newly created session
        """
        session_id = str(uuid4())
        now = datetime.now(UTC)
        expiration_duration = timedelta(seconds=expire_seconds)

        session = Session(
            id=session_id,
            user_fmu_directory=user_fmu_directory,
            created_at=now,
            expires_at=now + expiration_duration,
            last_accessed=now,
            access_tokens=AccessTokens(),
        )
        await self._store_session(session_id, session)

        return session_id

    async def get_session(self: Self, session_id: str) -> Session | ProjectSession:
        """Get the session data for a session id.

        Params:
            session_id: The session id being requested

        Returns:
            The session, if it exists and is valid

        Raises:
            SessionNotFoundError: If the session does not exist or is invalid
        """
        session = await self._retrieve_session(session_id)
        if not session:
            raise SessionNotFoundError("No active session found")

        now = datetime.now(UTC)
        if session.expires_at < now:
            await self.destroy_session(session_id)
            raise SessionNotFoundError("Invalid or expired session")

        session.last_accessed = now

        if isinstance(session, ProjectSession):
            lock = session.project_fmu_directory._lock
            try:
                if lock.is_acquired():
                    lock.refresh()
                session.lock_errors.refresh = None
            except Exception as e:
                session.lock_errors.refresh = str(e)

        await self._update_session(session_id, session)
        return session


session_manager = SessionManager()


async def create_fmu_session(
    user_fmu_directory: UserFMUDirectory,
    expire_seconds: int = settings.SESSION_EXPIRE_SECONDS,
) -> str:
    """Creates a new session and stores it in the session mananger."""
    return await session_manager.create_session(user_fmu_directory, expire_seconds)


async def add_fmu_project_to_session(
    session_id: str,
    project_fmu_directory: ProjectFMUDirectory,
) -> ProjectSession:
    """Adds an opened project FMU directory instance to the session.

    The session will attempt to acquire a write lock, but will proceed with
    read-only access if the lock cannot be acquired.

    Returns:
        The updated ProjectSession

    Raises:
        SessionNotFoundError: If no valid session was found
    """
    session = await session_manager.get_session(session_id)

    lock_errors = LockErrors()

    if isinstance(session, ProjectSession):
        try:
            session.project_fmu_directory._lock.release()
        except Exception as e:
            lock_errors.release = str(e)

    try:
        project_fmu_directory._lock.acquire()
    except Exception as e:
        lock_errors.acquire = str(e)

    lock_errors.refresh = None

    if isinstance(session, ProjectSession):
        project_session = session
        project_session.project_fmu_directory = project_fmu_directory
        project_session.lock_errors = lock_errors
    else:
        project_session = ProjectSession(
            **asdict(session),
            project_fmu_directory=project_fmu_directory,
            lock_errors=lock_errors,
        )
    add_to_user_recent_projects(
        project_path=project_fmu_directory.base_path,
        user_dir=project_session.user_fmu_directory,
    )
    await session_manager._store_session(session_id, project_session)
    return project_session


async def try_acquire_project_lock(session_id: str) -> ProjectSession:
    """Attempts to acquire or refresh the project lock for a session."""
    session = await session_manager.get_session(session_id)

    if not isinstance(session, ProjectSession):
        raise SessionNotFoundError("No FMU project directory open")

    lock = session.project_fmu_directory._lock

    try:
        if not lock.is_acquired():
            lock.acquire()
            session.lock_errors.acquire = None
    except Exception as e:
        session.lock_errors.acquire = str(e)

    await session_manager._store_session(session_id, session)
    return session


async def remove_fmu_project_from_session(session_id: str) -> Session:
    """Removes (closes) an open project FMU directory from a session.

    Returns:
        The updates session

    Raises:
        SessionNotFoundError: If no valid session was found
    """
    maybe_project_session = await session_manager.get_session(session_id)

    if not isinstance(maybe_project_session, ProjectSession):
        return maybe_project_session

    try:
        maybe_project_session.project_fmu_directory._lock.release()
        maybe_project_session.lock_errors.release = None
    except Exception as e:
        maybe_project_session.lock_errors.release = str(e)

    project_session_dict = asdict(maybe_project_session)
    project_session_dict.pop("project_fmu_directory", None)
    project_session_dict.pop("lock_errors", None)
    session = Session(**project_session_dict)
    await session_manager._store_session(session_id, session)
    return session


async def add_access_token_to_session(session_id: str, token: AccessToken) -> None:
    """Adds a known access token to the current session.

    Raises:
        SessionNotFoundError: If no valid session was found
    """
    if token.id not in AccessTokens.model_fields:
        raise ValueError("Invalid access token id")

    session = await session_manager.get_session(session_id)

    access_tokens_dict = session.access_tokens.model_dump()
    access_tokens_dict[token.id] = token.key
    session.access_tokens = AccessTokens.model_validate(access_tokens_dict)

    await session_manager._store_session(session_id, session)


async def destroy_fmu_session(session_id: str) -> None:
    """Destroys a session in the session manager."""
    await session_manager.destroy_session(session_id)
