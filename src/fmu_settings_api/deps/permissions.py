"""Permission dependencies."""

from fastapi import Depends, HTTPException

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
