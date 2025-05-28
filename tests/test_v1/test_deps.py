"""Tests dependencies (middleware)."""

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import Cookie, HTTPException, status
from fastapi.testclient import TestClient
from fmu.settings._init import init_user_fmu_directory

from fmu_settings_api.config import settings
from fmu_settings_api.deps import get_session
from fmu_settings_api.session import SessionManager

ROUTE = "/api/v1/health"


async def test_get_session_dep(
    tmp_path_mocked_home: Path, session_manager: SessionManager
) -> None:
    """Tests the get_session dependency."""
    with pytest.raises(HTTPException, match="401: No active session found"):
        await get_session(None)

    with pytest.raises(HTTPException, match="401: Invalid or expired session"):
        await get_session(Cookie(default=uuid4()))

    user_fmu_dir = init_user_fmu_directory()
    valid_session = await session_manager.create_session(user_fmu_dir)
    session = await get_session(valid_session)
    assert session.user_fmu_directory.path == user_fmu_dir.path

    with (
        patch(
            "fmu_settings_api.deps.session_manager.get_session",
            side_effect=Exception("foo"),
        ),
        pytest.raises(HTTPException, match="500: Session error: foo"),
    ):
        await get_session(Cookie(default=object))


def test_get_session_dep_from_request(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 401 returns when session id is not valid."""
    client_with_session.cookies.set(settings.SESSION_COOKIE_KEY, str(uuid4()))
    response = client_with_session.get(ROUTE)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
