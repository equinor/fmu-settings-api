"""Authentication dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from fmu_settings_api.config import HttpHeader, settings

api_token_header = APIKeyHeader(name=HttpHeader.API_TOKEN_KEY)

TokenHeaderDep = Annotated[str, Security(api_token_header)]


async def verify_auth_token(req_token: TokenHeaderDep) -> TokenHeaderDep:
    """Verifies the request token vs the stored one."""
    if req_token != settings.TOKEN:
        raise HTTPException(status_code=401, detail="Not authorized")
    return req_token


AuthTokenDep = Annotated[TokenHeaderDep, Depends(verify_auth_token)]
