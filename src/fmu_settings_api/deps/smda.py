"""SMDA dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException

from fmu_settings_api.config import HttpHeader
from fmu_settings_api.interfaces.smda_api import SmdaAPI
from fmu_settings_api.services.smda import SmdaService
from fmu_settings_api.session import ProjectSession, Session

from .session import ProjectSmdaSessionDep, SessionDep


async def get_smda_api(session: Session | ProjectSession) -> SmdaAPI:
    """Returns an Smda api object for the given session."""
    if session.access_tokens.smda_api is None:
        raise HTTPException(
            status_code=401,
            detail="SMDA access token is not set",
            headers={HttpHeader.UPSTREAM_SOURCE_KEY: HttpHeader.UPSTREAM_SOURCE_SMDA},
        )

    return SmdaAPI(
        access_token=session.access_tokens.smda_api.get_secret_value(),
        subscription_key=session.user_fmu_directory.get_config_value(
            "user_api_keys.smda_subscription"
        ).get_secret_value(),
    )


async def get_smda_interface(session: SessionDep) -> SmdaAPI:
    """Returns an Smda interface for the .fmu session."""
    return await get_smda_api(session)


SmdaInterfaceDep = Annotated[SmdaAPI, Depends(get_smda_interface)]


async def get_project_smda_interface(session: ProjectSmdaSessionDep) -> SmdaAPI:
    """Returns an Smda interface for the project .fmu session."""
    return await get_smda_api(session)


ProjectSmdaInterfaceDep = Annotated[SmdaAPI, Depends(get_project_smda_interface)]


async def get_smda_service(smda_api: SmdaInterfaceDep) -> SmdaService:
    """Returns an SmdaService instance for the session."""
    return SmdaService(smda_api)


SmdaServiceDep = Annotated[SmdaService, Depends(get_smda_service)]


async def get_project_smda_service(smda_api: ProjectSmdaInterfaceDep) -> SmdaService:
    """Returns an SmdaService instance for the project session."""
    return SmdaService(smda_api)


ProjectSmdaServiceDep = Annotated[SmdaService, Depends(get_project_smda_service)]
