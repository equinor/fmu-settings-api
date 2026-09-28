"""Sumo service dependency."""

from typing import Annotated

from fastapi import Depends

from fmu_settings_api.services.sumo import SumoService


def get_sumo_service() -> SumoService:
    """Return a Sumo service."""
    return SumoService()


SumoServiceDep = Annotated[SumoService, Depends(get_sumo_service)]
