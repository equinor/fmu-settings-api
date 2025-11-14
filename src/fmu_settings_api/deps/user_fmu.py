"""User FMU directory dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException
from fmu.settings._fmu_dir import UserFMUDirectory
from fmu.settings._init import init_user_fmu_directory


async def ensure_user_fmu_directory() -> UserFMUDirectory:
    """Ensures the user's FMU Directory exists.

    Returns:
        The user's UserFMUDirectory
    """
    try:
        return UserFMUDirectory()
    except FileNotFoundError:
        try:
            return init_user_fmu_directory()
        except PermissionError as e:
            raise HTTPException(
                status_code=403,
                detail="Permission denied creating user .fmu",
            ) from e
        except FileExistsError as e:
            raise HTTPException(
                status_code=409,
                detail=(
                    "User .fmu already exists but is invalid (i.e. is not a directory)"
                ),
            ) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail="Permission denied creating user .fmu",
        ) from e
    except FileExistsError as e:
        raise HTTPException(
            status_code=409,
            detail="User .fmu already exists but is invalid (i.e. is not a directory)",
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


UserFMUDirDep = Annotated[UserFMUDirectory, Depends(ensure_user_fmu_directory)]
