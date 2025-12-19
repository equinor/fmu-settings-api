"""Match service dependencies."""

from typing import Annotated

from fastapi import Depends

from fmu_settings_api.services.match import MatchService


async def get_match_service() -> MatchService:
    """Returns a MatchService instance."""
    return MatchService()


MatchServiceDep = Annotated[MatchService, Depends(get_match_service)]
