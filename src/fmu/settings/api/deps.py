"""Dependencies injected into FastAPI."""

from typing import Annotated

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from fmu.settings.api.config import settings

api_token_header = APIKeyHeader(name=settings.TOKEN_HEADER_NAME)

TokenHeaderDep = Annotated[str, Security(api_token_header)]


def verify_auth_token(req_token: TokenHeaderDep) -> TokenHeaderDep:
    """Verifies the request token vs the stored one."""
    if req_token != settings.TOKEN:
        raise HTTPException(status_code=401, detail="Not authorized")
    return req_token
