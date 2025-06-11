"""Routes to operate on the .fmu config file."""

from textwrap import dedent
from typing import Final

from fastapi import APIRouter, HTTPException
from fmu.settings.models.user_config import UserAPIKeys, UserConfig

from fmu_settings_api.deps import SessionDep
from fmu_settings_api.models.common import APIKey, Message
from fmu_settings_api.v1.responses import (
    GetSessionResponses,
    Responses,
    inline_add_response,
)

router = APIRouter(prefix="/user", tags=["user"])

UserResponses: Final[Responses] = {
    **inline_add_response(
        403,
        "The OS returned a permissions error while locating or creating .fmu",
        [
            {"detail": "Permission denied loading user .fmu config at {config.path}"},
        ],
    ),
    **inline_add_response(
        404,
        dedent(
            """
            The .fmu directory was unable to be found at or above a given path, or
            the requested path to create a project .fmu directory at does not exist.
            """
        ),
        [
            {"detail": "User .fmu config at {config.path} does not exist"},
        ],
    ),
}


@router.get(
    "/",
    response_model=UserConfig,
    summary="Returns the user .fmu configuration",
    description=dedent(
        """
        The user configuration can store API subscription keys or tokens. These are
        obfuscated as '**********' when returned.
        """
    ),
    responses={
        **GetSessionResponses,
        **UserResponses,
    },
)
async def get_user(session: SessionDep) -> UserConfig:
    """Returns the user configuration of the current session."""
    try:
        config = session.user_fmu_directory.config
        return config.load().obfuscate_secrets()
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


@router.patch(
    "/api_key",
    response_model=Message,
    summary="Saves an API key/token to the user .fmu configuration",
    description=dedent(
        f"""
        Currently only known API's can be saved to the user .fmu configuration.
        Arbitrary API key-value pairs cannot be saved. The currently known APIs are:

        {", ".join(UserAPIKeys.model_fields.keys())}
        """
    ),
    responses={
        **GetSessionResponses,
        **UserResponses,
        **inline_add_response(
            400,
            dedent(
                """
                Occurs when trying to save a key to an unknown API. An API is unknown
                if it is not a predefined field in the fmu-settings UserAPIKeys model.
                """
            ),
            [
                {"detail": "API id {api_key.id} is not known or supported"},
            ],
        ),
    },
)
async def patch_api_key(
    session: SessionDep,
    api_key: APIKey,
) -> Message:
    """Patches the API key for a known and supported API."""
    if api_key.id not in UserAPIKeys.model_fields:
        raise HTTPException(
            status_code=400, detail=f"API id {api_key.id} is not known or supported"
        )

    try:
        session.user_fmu_directory.set_config_value(
            f"user_api_keys.{api_key.id}", api_key.key
        )
        return Message(message=f"Saved API key for {api_key.id}")
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=(
                "Permission denied loading user .fmu config at "
                f"{session.user_fmu_directory.config.path}"
            ),
        ) from e
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
