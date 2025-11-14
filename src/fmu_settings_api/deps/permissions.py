"""Permission dependencies."""

from fastapi import Cookie, Depends, HTTPException

from fmu_settings_api.config import HttpHeader
from fmu_settings_api.session import SessionNotFoundError, refresh_project_lock

from .session import ProjectSessionDep


async def check_write_permissions(project_session: ProjectSessionDep) -> None:
    """Check if the project allows write operations.

    Args:
        project_session: The project session containing the FMU directory.

    Raises:
        HTTPException: If the project is read-only due to lock conflicts.
    """
    fmu_dir = project_session.project_fmu_directory
    try:
        if not fmu_dir._lock.is_locked(propagate_errors=True):
            raise HTTPException(
                status_code=423,
                detail="Project is not locked. Acquire the lock before writing.",
            )
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied accessing .fmu at {fmu_dir.path}",
        ) from e
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=423,
            detail="Project lock file is missing. Project is treated as read-only.",
        ) from e
    if not fmu_dir._lock.is_acquired():
        raise HTTPException(
            status_code=423,
            detail=(
                "Project is read-only. Cannot write to project "
                "that is locked by another process."
            ),
        )


WritePermissionDep = Depends(check_write_permissions)


async def refresh_project_lock_dep(
    fmu_settings_session: str | None = Cookie(None),
) -> None:
    """Refreshes the project lock for write operations."""
    if not fmu_settings_session:
        raise HTTPException(
            status_code=401,
            detail="No active session found",
            headers={
                HttpHeader.WWW_AUTHENTICATE_KEY: HttpHeader.WWW_AUTHENTICATE_COOKIE
            },
        )
    try:
        await refresh_project_lock(fmu_settings_session)
    except SessionNotFoundError as e:
        raise HTTPException(
            status_code=401,
            detail="No FMU project directory open",
            headers={
                HttpHeader.WWW_AUTHENTICATE_KEY: HttpHeader.WWW_AUTHENTICATE_COOKIE
            },
        ) from e
    except Exception:
        pass


RefreshLockDep = Depends(refresh_project_lock_dep)
