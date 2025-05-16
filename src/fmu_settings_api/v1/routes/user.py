"""Routes to operate on the .fmu config file."""

from fastapi import APIRouter, HTTPException
from fmu.settings.models.user_config import UserAPIKeys, UserConfig

from fmu_settings_api.deps import SessionDep
from fmu_settings_api.models.common import APIKey, Message

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/", response_model=UserConfig)
async def get_fmu_directory_config(session: SessionDep) -> UserConfig:
    """Returns the user configuration of the current session."""
    try:
        config = session.user_fmu_directory.config
        config_dict = config.load().model_dump()

        # Overwrite secret keys with obfuscated keys
        for k, v in config_dict["user_api_keys"].items():
            if v is not None:
                # Convert SecretStr("*********") to "*********"
                config_dict["user_api_keys"][k] = str(v)

        return UserConfig.model_validate(config_dict)
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied loading user .fmu config at {config.path}",
        ) from e
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404, detail=f"User .fmu config at {config.path} does not exist"
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.patch("/api_key")
async def patch_api_token_key(
    session: SessionDep,
    api_key: APIKey,
) -> Message:
    """Patches the API key for a known and supported API."""
    if api_key.id not in UserAPIKeys.model_fields:
        raise HTTPException(
            status_code=422, detail=f"API id {api_key.id} is not known or supported"
        )

    try:
        session.user_fmu_directory.set_config_value(
            f"user_api_keys.{api_key.id}", api_key.key
        )
        return Message(message=f"Saved API key for {api_key.id}")
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=(
                f"User .fmu config at {session.user_fmu_directory.config.path} does "
                "not exist"
            ),
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
