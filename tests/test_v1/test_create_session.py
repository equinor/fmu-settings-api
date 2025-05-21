"""Tests the /api/v1/session routes."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from fmu.settings._fmu_dir import UserFMUDirectory
from fmu.settings._init import init_fmu_directory, init_user_fmu_directory
from pytest import MonkeyPatch

from fmu_settings_api.__main__ import app
from fmu_settings_api.config import settings
from fmu_settings_api.models import FMUProject, SessionResponse
from fmu_settings_api.session import ProjectSession, Session, SessionManager

client = TestClient(app)

ROUTE = "/api/v1/session"


def test_get_session_no_token() -> None:
    """Tests the fmu routes require a session."""
    response = client.post(ROUTE)
    assert response.status_code == status.HTTP_403_FORBIDDEN, response.json()
    assert response.json() == {"detail": "Not authenticated"}


def test_get_session_invalid_token() -> None:
    """Tests the fmu routes require a session."""
    bad_token = "no" * 32
    response = client.post(ROUTE, headers={settings.TOKEN_HEADER_NAME: bad_token})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "Not authorized"}


def test_get_session_no_token_does_not_create_user_fmu(
    tmp_path_mocked_home: Path,
) -> None:
    """Tests unauthenticated requests do not create a user .fmu."""
    response = client.post(ROUTE)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Not authenticated"}
    assert not (tmp_path_mocked_home / "home/.fmu").exists()


def test_get_session_invalid_token_does_not_create_user_fmu(
    tmp_path_mocked_home: Path,
) -> None:
    """Tests unauthorized requests do not create a user .fmu."""
    bad_token = "no" * 32
    response = client.post(ROUTE, headers={settings.TOKEN_HEADER_NAME: bad_token})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "Not authorized"}
    assert not (tmp_path_mocked_home / "home/.fmu").exists()


def test_get_session_create_user_fmu_no_permissions(
    user_fmu_dir_no_permissions: Path, mock_token: str
) -> None:
    """Tests that user .fmu directory permissions errors return a 403."""
    response = client.post(ROUTE, headers={settings.TOKEN_HEADER_NAME: mock_token})
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Permission denied creating user .fmu"}


def test_get_session_creating_user_fmu_exists_as_a_file(
    tmp_path_mocked_home: Path, mock_token: str, monkeypatch: MonkeyPatch
) -> None:
    """Tests that a user .fmu as a file raises a 409."""
    (tmp_path_mocked_home / "home/.fmu").touch()
    monkeypatch.chdir(tmp_path_mocked_home)
    response = client.post(ROUTE, headers={settings.TOKEN_HEADER_NAME: mock_token})
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {
        "detail": "User .fmu already exists but is invalid (i.e. is not a directory)"
    }


def test_get_session_creating_user_unknown_failure(
    tmp_path_mocked_home: Path, mock_token: str, monkeypatch: MonkeyPatch
) -> None:
    """Tests that an unknown exception returns 500."""
    with patch(
        "fmu_settings_api.deps.init_user_fmu_directory",
        side_effect=Exception("foo"),
    ):
        user_fmu_path = tmp_path_mocked_home / "home/.fmu"
        assert not user_fmu_path.exists()

        monkeypatch.chdir(tmp_path_mocked_home)
        init_fmu_directory(tmp_path_mocked_home)
        response = client.post(ROUTE, headers={settings.TOKEN_HEADER_NAME: mock_token})
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_get_session_creates_user_fmu(
    tmp_path_mocked_home: Path,
    mock_token: str,
    session_manager: SessionManager,
) -> None:
    """Tests that user .fmu is created when a session is created."""
    user_home = tmp_path_mocked_home / "home"
    with pytest.raises(
        FileNotFoundError, match=f"No .fmu directory found at {user_home}"
    ):
        UserFMUDirectory()

    response = client.post(ROUTE, headers={settings.TOKEN_HEADER_NAME: mock_token})
    assert response.status_code == status.HTTP_200_OK, response.json()
    # Does not raise
    user_fmu_dir = UserFMUDirectory()
    assert (
        json.dumps(response.json(), separators=(",", ":"))
        == SessionResponse(user_config=user_fmu_dir.config.load()).model_dump_json()
    )
    assert user_fmu_dir.path == user_home / ".fmu"


async def test_get_session_creates_session(
    tmp_path_mocked_home: Path,
    mock_token: str,
    session_manager: SessionManager,
) -> None:
    """Tests that user .fmu is created when a session is created."""
    user_home = tmp_path_mocked_home / "home"
    response = client.post(ROUTE, headers={settings.TOKEN_HEADER_NAME: mock_token})
    assert response.status_code == status.HTTP_200_OK, response.json()

    user_fmu_dir = UserFMUDirectory()
    assert user_fmu_dir.path == user_home / ".fmu"

    session_id = response.cookies.get(settings.SESSION_COOKIE_KEY)
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert session is not None
    assert isinstance(session, Session)
    assert session.user_fmu_directory.path == user_fmu_dir.path
    assert session.user_fmu_directory.config.load() == user_fmu_dir.config.load()


async def test_get_session_finds_existing_user_fmu(
    tmp_path_mocked_home: Path,
    mock_token: str,
    session_manager: SessionManager,
) -> None:
    """Tests that an existing user .fmu directory is located with a session."""
    user_fmu_dir = init_user_fmu_directory()

    response = client.post(ROUTE, headers={settings.TOKEN_HEADER_NAME: mock_token})
    assert response.status_code == status.HTTP_200_OK, response.json()

    session_id = response.cookies.get(settings.SESSION_COOKIE_KEY)
    assert session_id is not None

    session = await session_manager.get_session(session_id)
    assert session is not None

    assert isinstance(session, Session)
    assert session.user_fmu_directory.path == user_fmu_dir.path


async def test_get_session_from_project_path_returns_fmu_project(
    tmp_path_mocked_home: Path,
    mock_token: str,
    monkeypatch: MonkeyPatch,
    session_manager: SessionManager,
) -> None:
    """Tests that user .fmu is created when a session is created."""
    user_fmu_dir = init_user_fmu_directory()
    project_fmu_dir = init_fmu_directory(tmp_path_mocked_home)
    ert_model_path = tmp_path_mocked_home / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    response = client.post(ROUTE, headers={settings.TOKEN_HEADER_NAME: mock_token})
    assert response.status_code == status.HTTP_200_OK, response.json()
    # Does not raise
    user_fmu_dir = UserFMUDirectory()
    assert (
        json.dumps(response.json(), separators=(",", ":"))
        == SessionResponse(
            user_config=user_fmu_dir.config.load(),
            fmu_project=FMUProject(
                path=tmp_path_mocked_home,
                project_dir_name=tmp_path_mocked_home.name,
                config=project_fmu_dir.config.load(),
            ),
        ).model_dump_json()
    )
    assert user_fmu_dir.path == user_fmu_dir.path

    session_id = response.cookies.get(settings.SESSION_COOKIE_KEY)
    assert session_id is not None

    session = await session_manager.get_session(session_id)
    assert session is not None
    assert isinstance(session, ProjectSession)

    assert session.user_fmu_directory.path == user_fmu_dir.path
    assert session.user_fmu_directory.config.load() == user_fmu_dir.config.load()

    assert session.project_fmu_directory.path == project_fmu_dir.path
    assert session.project_fmu_directory.config.load() == project_fmu_dir.config.load()
