"""Service for managing session operations and business logic."""

from pathlib import Path
from typing import cast

from fmu.settings import (
    ProjectFMUDirectory,
    find_nearest_fmu_directory,
    get_fmu_directory,
)
from fmu.settings._init import init_fmu_directory

from fmu_settings_api.config import settings
from fmu_settings_api.models import AccessToken, SessionResponse
from fmu_settings_api.models.project import LockStatus
from fmu_settings_api.services.user import remove_from_recent_projects
from fmu_settings_api.session import (
    ProjectSession,
    Session,
    add_access_token_to_session as add_token_to_session_manager,
    add_fmu_project_to_session,
    remove_fmu_project_from_session,
    try_acquire_project_lock,
)


class SessionService:
    """Service for handling session business logic."""

    def __init__(self, session: Session | ProjectSession) -> None:
        """Initialize the service with a session."""
        self._session = session

    def get_session_response(self) -> SessionResponse:
        """Get the session data in a serializable format."""
        return SessionResponse(
            id=self._session.id,
            created_at=self._session.created_at,
            expires_at=self._session.expires_at,
            last_accessed=self._session.last_accessed,
        )

    async def add_access_token(self, access_token: AccessToken) -> str:
        """Add a known access token to the session."""
        await add_token_to_session_manager(self._session.id, access_token)
        return f"Set session access token for {access_token.id}"

    async def get_or_find_project(self) -> ProjectFMUDirectory:
        """Get the project from session or find nearest project .fmu directory."""
        if isinstance(self._session, ProjectSession):
            return self._session.project_fmu_directory

        path = Path.cwd()
        fmu_dir = find_nearest_fmu_directory(
            path, lock_timeout_seconds=settings.SESSION_EXPIRE_SECONDS
        )
        await add_fmu_project_to_session(self._session.id, fmu_dir)
        return fmu_dir

    async def attach_project(self, path: Path) -> ProjectFMUDirectory:
        """Open a project .fmu directory at the specified path."""
        if not path.exists():
            remove_from_recent_projects(path, self._session.user_fmu_directory)
            raise FileNotFoundError(f"Path {path} does not exist")

        fmu_dir = get_fmu_directory(
            path, lock_timeout_seconds=settings.SESSION_EXPIRE_SECONDS
        )
        await add_fmu_project_to_session(self._session.id, fmu_dir)
        return fmu_dir

    async def initialize_project(self, path: Path) -> ProjectFMUDirectory:
        """Initialize a new project .fmu directory at the specified path."""
        fmu_dir = init_fmu_directory(
            path,
            lock_timeout_seconds=settings.SESSION_EXPIRE_SECONDS,
        )
        await add_fmu_project_to_session(self._session.id, fmu_dir)
        return fmu_dir

    async def close_project(self) -> str:
        """Remove (close) a project .fmu directory from the session."""
        project_session = cast("ProjectSession", self._session)
        project_path = project_session.project_fmu_directory.path
        await remove_fmu_project_from_session(self._session.id)
        return f"FMU directory {project_path} closed successfully"

    async def acquire_project_lock(self) -> str:
        """Attempt to acquire the project lock for editing."""
        updated_session = await try_acquire_project_lock(self._session.id)
        lock = updated_session.project_fmu_directory._lock

        if lock.is_acquired():
            return "Project lock acquired."

        return (
            "Project remains read-only because the lock could not be acquired."
            "Check lock status for details."
        )

    def get_lock_status(self) -> LockStatus:
        """Get the lock status including session-specific error information."""
        project_session = cast("ProjectSession", self._session)
        fmu_dir = project_session.project_fmu_directory

        is_lock_acquired = False
        lock_file_exists = False
        lock_info = None
        lock_status_error = None
        lock_file_read_error = None

        try:
            is_lock_acquired = fmu_dir._lock.is_acquired()
        except Exception as e:
            lock_status_error = f"Failed to check lock status: {str(e)}"

        try:
            if fmu_dir._lock.exists:
                lock_file_exists = True
                try:
                    lock_info = fmu_dir._lock.load(force=True, store_cache=False)
                except (OSError, PermissionError) as e:
                    lock_file_read_error = f"Failed to read lock file: {str(e)}"
                except ValueError as e:
                    lock_file_read_error = f"Failed to parse lock file: {str(e)}"
                except Exception as e:
                    lock_file_read_error = f"Failed to process lock file: {str(e)}"
            else:
                lock_file_exists = False
        except Exception as e:
            lock_file_read_error = f"Failed to access lock file path: {str(e)}"

        return LockStatus(
            is_lock_acquired=is_lock_acquired,
            lock_file_exists=lock_file_exists,
            lock_info=lock_info,
            lock_status_error=lock_status_error,
            lock_file_read_error=lock_file_read_error,
            last_lock_acquire_error=project_session.lock_errors.acquire,
            last_lock_release_error=project_session.lock_errors.release,
            last_lock_refresh_error=project_session.lock_errors.refresh,
        )
