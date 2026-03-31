"""Functionality for managing sessions."""

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Self
from uuid import uuid4

from fmu.settings import ProjectFMUDirectory
from fmu.settings._fmu_dir import UserFMUDirectory
from pydantic import BaseModel, SecretStr
from runrms.api import RmsApiProxy
from runrms.executor import ApiExecutor

from fmu_settings_api.config import settings
from fmu_settings_api.logging import get_logger
from fmu_settings_api.models.common import AccessToken
from fmu_settings_api.services.user import add_to_user_recent_projects

logger = get_logger(__name__)


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
class RmsSession:
    """Stores RMS-session references."""

    executor: ApiExecutor
    """The RMS API executor controlling the worker lifetime."""
    project: RmsApiProxy
    """An opened RMS project that close() can be called against."""
    expires_at: datetime
    """Timestamp when the RMS session will expire."""

    def cleanup(self, session_id: str = "unknown") -> None:
        """Closes the RMS project and shuts down the executor."""
        try:
            self.project.close()
        except Exception as e:
            logger.error(
                "rms_project_close_failed",
                session_id=session_id,
                error=str(e),
                error_type=type(e).__name__,
            )
        try:
            self.executor.shutdown()
        except Exception as e:
            logger.error(
                "rms_executor_shutdown_failed",
                session_id=session_id,
                error=str(e),
                error_type=type(e).__name__,
            )


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
    rms_session: RmsSession | None = None


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

    async def update_session(
        self: Self, session_id: str, session: Session | ProjectSession
    ) -> None:
        """Stores an updated session back into the session backend."""
        self.storage[session_id] = session

    async def destroy_session(self: Self, session_id: str) -> None:
        """Destroys a session by its session id."""
        session = await self._retrieve_session(session_id)
        if session is None:
            return

        if isinstance(session, ProjectSession):
            try:
                session.project_fmu_directory._lock.release()
            except Exception as e:
                session.lock_errors.release = str(e)
                logger.error(
                    "destroy_session_release_lock",
                    session_id=session_id,
                    error=str(e),
                    error_type=type(e).__name__,
                )

            if session.rms_session is not None:
                session.rms_session.cleanup(session_id)
                session.rms_session = None

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
        expires_at = now + timedelta(seconds=expire_seconds)

        session = Session(
            id=session_id,
            user_fmu_directory=user_fmu_directory,
            created_at=now,
            expires_at=expires_at,
            last_accessed=now,
            access_tokens=AccessTokens(),
        )
        await self._store_session(session_id, session)

        return session_id

    async def renew_session(
        self: Self,
        session_id: str,
        expire_seconds: int = settings.SESSION_EXPIRE_SECONDS,
    ) -> Session | ProjectSession:
        """Renews an existing session by rotating its id and expiration.

        Returns:
            The renewed session instance stored under its new session id

        Raises:
            SessionNotFoundError: If the session does not exist
        """
        session = await self._retrieve_session(session_id)
        if session is None:
            raise SessionNotFoundError("No active session found")

        now = datetime.now(UTC)
        new_session_id = str(uuid4())
        session.id = new_session_id
        session.created_at = now
        session.expires_at = now + timedelta(seconds=expire_seconds)
        session.last_accessed = now

        del self.storage[session_id]
        await self._store_session(new_session_id, session)
        return session

    async def get_session(self: Self, session_id: str) -> Session | ProjectSession:
        """Get the session data for a session id.

        Params:
            session_id: The session id being requested

        Returns:
            The session, if it exists and is valid

        Raises:
            SessionNotFoundError: If the session does not exist
        """
        session = await self._retrieve_session(session_id)
        if not session:
            raise SessionNotFoundError("No active session found")

        session.last_accessed = datetime.now(UTC)

        await self.update_session(session_id, session)
        return session


session_manager = SessionManager()


# Wrapper functions for the Session Manager singleton


async def create_fmu_session(
    user_fmu_directory: UserFMUDirectory,
    expire_seconds: int = settings.SESSION_EXPIRE_SECONDS,
) -> str:
    """Creates a new session and stores it in the session mananger."""
    return await session_manager.create_session(user_fmu_directory, expire_seconds)


async def get_fmu_session(session_id: str) -> Session | ProjectSession:
    """Gets a session from the session manager."""
    return await session_manager.get_session(session_id)


async def renew_fmu_session(
    session_id: str,
    expire_seconds: int = settings.SESSION_EXPIRE_SECONDS,
) -> Session | ProjectSession:
    """Renews a session in the session manager."""
    return await session_manager.renew_session(session_id, expire_seconds)


async def update_fmu_session(session: Session | ProjectSession) -> None:
    """Update a session in the session manager."""
    await session_manager.update_session(session.id, session)


async def destroy_fmu_session_if_expired(session_id: str) -> None:
    """Destroys the expired sessions in the session manager for the given session_id.

    Checks the user and rms session for the given session_id and destroy the ones
    that has expired.
    """
    try:
        session = await get_fmu_session(session_id)
    except SessionNotFoundError:
        return
    now = datetime.now(UTC)
    rms_session_expiration = await get_rms_session_expiration(session.id)
    if rms_session_expiration is not None and rms_session_expiration < now:
        await remove_rms_project_from_session(session.id)

    if session.expires_at < now:
        await session_manager.destroy_session(session_id)


async def refresh_rms_session(project_session: ProjectSession) -> RmsSession:
    """Refresh the expiration time for an opened RMS session."""
    rms_session = project_session.rms_session
    if rms_session is None:
        raise SessionNotFoundError("No RMS project is currently open")

    rms_session.expires_at = datetime.now(UTC) + timedelta(
        seconds=settings.RMS_SESSION_EXPIRE_SECONDS
    )
    await update_fmu_session(project_session)
    return rms_session


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
    session = await get_fmu_session(session_id)

    lock_errors = LockErrors()

    if isinstance(session, ProjectSession):
        try:
            session.project_fmu_directory._lock.release()
        except Exception as e:
            lock_errors.release = str(e)

        if session.rms_session is not None:
            session.rms_session.cleanup(session_id)
            session.rms_session = None

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
    await update_fmu_session(project_session)
    return project_session


async def add_access_token_to_session(session_id: str, token: AccessToken) -> None:
    """Adds a known access token to the current session.

    Raises:
        SessionNotFoundError: If no valid session was found
    """
    if token.id not in AccessTokens.model_fields:
        raise ValueError("Invalid access token id")

    session = await get_fmu_session(session_id)

    access_tokens_dict = session.access_tokens.model_dump()
    access_tokens_dict[token.id] = token.key
    session.access_tokens = AccessTokens.model_validate(access_tokens_dict)

    await update_fmu_session(session)


async def try_acquire_project_lock(session_id: str) -> ProjectSession:
    """Attempts to acquire the project lock for a session.

    Returns:
        The ProjectSession with updated lock error state

    Raises:
        SessionNotFoundError: If no valid session or project is found
    """
    session = await get_fmu_session(session_id)

    if not isinstance(session, ProjectSession):
        raise SessionNotFoundError("No FMU project directory open")

    lock = session.project_fmu_directory._lock

    try:
        if not lock.is_acquired():
            lock.acquire()
            session.lock_errors.acquire = None
    except Exception as e:
        session.lock_errors.acquire = str(e)

    await update_fmu_session(session)
    return session


async def release_project_lock(session_id: str) -> ProjectSession:
    """Releases the project lock for a session if it is currently held.

    Returns:
        The ProjectSession with updated lock error state

    Raises:
        SessionNotFoundError: If no valid session or project is found
    """
    session = await get_fmu_session(session_id)

    if not isinstance(session, ProjectSession):
        raise SessionNotFoundError("No FMU project directory open")

    lock = session.project_fmu_directory._lock

    try:
        if lock.is_acquired():
            lock.release()
            session.lock_errors.release = None
    except Exception as e:
        session.lock_errors.release = str(e)

    await update_fmu_session(session)
    return session


async def refresh_project_lock(session_id: str) -> ProjectSession:
    """Refreshes the project lock if it is currently held by this session.

    This should be called on write operations to extend the lock timeout.

    Returns:
        The ProjectSession with updated lock error state

    Raises:
        SessionNotFoundError: If no valid session or project is found
    """
    session = await get_fmu_session(session_id)

    if not isinstance(session, ProjectSession):
        raise SessionNotFoundError("No FMU project directory open")

    lock = session.project_fmu_directory._lock
    try:
        if lock.is_acquired():
            lock.refresh()
        session.lock_errors.refresh = None
    except Exception as e:
        session.lock_errors.refresh = str(e)

    await update_fmu_session(session)
    return session


async def remove_fmu_project_from_session(session_id: str) -> Session:
    """Removes (closes) an open project FMU directory from a session.

    Returns:
        The updates session

    Raises:
        SessionNotFoundError: If no valid session was found
    """
    maybe_project_session = await get_fmu_session(session_id)

    if not isinstance(maybe_project_session, ProjectSession):
        return maybe_project_session

    try:
        maybe_project_session.project_fmu_directory._lock.release()
        maybe_project_session.lock_errors.release = None
    except Exception as e:
        maybe_project_session.lock_errors.release = str(e)

    if maybe_project_session.rms_session is not None:
        maybe_project_session.rms_session.cleanup(session_id)
        maybe_project_session.rms_session = None

    project_session_dict = asdict(maybe_project_session)
    project_session_dict.pop("project_fmu_directory", None)
    project_session_dict.pop("lock_errors", None)
    project_session_dict.pop("rms_session", None)

    session = Session(**project_session_dict)
    await update_fmu_session(session)
    return session


async def add_rms_project_to_session(
    session_id: str, executor: ApiExecutor, rms_project: RmsApiProxy
) -> ProjectSession:
    """Adds an opened RMS project to the session.

    Returns:
        The updated ProjectSession

    Raises:
        SessionNotFoundError: If no valid session was found
    """
    session = await get_fmu_session(session_id)

    if not isinstance(session, ProjectSession):
        raise SessionNotFoundError("No FMU project directory open")

    if session.rms_session is not None:
        session.rms_session.cleanup(session_id)

    rms_expires_at = datetime.now(UTC) + timedelta(
        seconds=settings.RMS_SESSION_EXPIRE_SECONDS
    )
    session.rms_session = RmsSession(
        executor=executor, project=rms_project, expires_at=rms_expires_at
    )
    await update_fmu_session(session)
    return session


async def remove_rms_project_from_session(session_id: str) -> ProjectSession:
    """Removes (closes) an open RMS project from a project session.

    If `cleanup` is False, the RMS worker and project will not be cleaned up. This is
    useful when preserving an opened project to a new session.

    Returns:
        The updated ProjectSession with rms_session set to None

    Raises:
        SessionNotFoundError: If no valid session was found
    """
    session = await get_fmu_session(session_id)

    if not isinstance(session, ProjectSession):
        raise SessionNotFoundError("No FMU project directory open")

    if session.rms_session is not None:
        session.rms_session.cleanup(session_id)

    session.rms_session = None

    await update_fmu_session(session)
    return session


async def get_rms_session_expiration(session_id: str) -> datetime | None:
    """Get the expiration time of an RMS session.

    If the user session with session_id contains an open RMS session,
    the expiration time of this RMS session is returned.
    """
    session = await get_fmu_session(session_id)
    if isinstance(session, ProjectSession) and session.rms_session is not None:
        return session.rms_session.expires_at
    return None
