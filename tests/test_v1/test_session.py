"""Tests the /api/v1/session routes."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from fmu.settings._fmu_dir import UserFMUDirectory
from fmu.settings._init import init_fmu_directory, init_user_fmu_directory
from fmu.settings._resources.lock_manager import LockError
from pydantic import SecretStr
from pytest import MonkeyPatch

from fmu_settings_api.__main__ import app
from fmu_settings_api.config import HttpHeader, settings
from fmu_settings_api.session import (
    ProjectSession,
    Session,
    SessionManager,
    SessionNotFoundError,
)

ROUTE = "/api/v1/session"


def test_get_session_no_token() -> None:
    """Tests the fmu routes require a session."""
    client = TestClient(app)
    response = client.post(ROUTE)
    assert response.status_code == status.HTTP_403_FORBIDDEN, response.json()
    assert response.json() == {"detail": "Not authenticated"}


def test_get_session_invalid_token() -> None:
    """Tests the fmu routes require a session."""
    client = TestClient(app)
    bad_token = "no" * 32
    response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: bad_token})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "Not authorized"}


def test_get_session_no_token_does_not_create_user_fmu(
    tmp_path_mocked_home: Path,
) -> None:
    """Tests unauthenticated requests do not create a user .fmu."""
    client = TestClient(app)
    response = client.post(ROUTE)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Not authenticated"}
    assert not (tmp_path_mocked_home / "home/.fmu").exists()


def test_get_session_invalid_token_does_not_create_user_fmu(
    tmp_path_mocked_home: Path,
) -> None:
    """Tests unauthorized requests do not create a user .fmu."""
    client = TestClient(app)
    bad_token = "no" * 32
    response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: bad_token})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "Not authorized"}
    assert not (tmp_path_mocked_home / "home/.fmu").exists()


def test_get_session_create_user_fmu_no_permissions(
    user_fmu_dir_no_permissions: Path, mock_token: str
) -> None:
    """Tests that user .fmu directory permissions errors return a 403."""
    client = TestClient(app)
    response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Permission denied creating user .fmu"}


def test_get_session_creating_user_fmu_exists_as_a_file(
    tmp_path_mocked_home: Path, mock_token: str, monkeypatch: MonkeyPatch
) -> None:
    """Tests that a user .fmu as a file raises a 409."""
    client = TestClient(app)
    (tmp_path_mocked_home / "home/.fmu").touch()
    monkeypatch.chdir(tmp_path_mocked_home)
    response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {
        "detail": "User .fmu already exists but is invalid (i.e. is not a directory)"
    }


def test_get_session_creating_user_unknown_failure(
    tmp_path_mocked_home: Path, mock_token: str, monkeypatch: MonkeyPatch
) -> None:
    """Tests that an unknown exception returns 500."""
    client = TestClient(app)
    with patch(
        "fmu_settings_api.deps.init_user_fmu_directory",
        side_effect=Exception("foo"),
    ):
        user_fmu_path = tmp_path_mocked_home / "home/.fmu"
        assert not user_fmu_path.exists()

        monkeypatch.chdir(tmp_path_mocked_home)
        init_fmu_directory(tmp_path_mocked_home)
        response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_get_session_creates_user_fmu(
    tmp_path_mocked_home: Path,
    mock_token: str,
    session_manager: SessionManager,
) -> None:
    """Tests that user .fmu is created when a session is created."""
    client = TestClient(app)
    user_home = tmp_path_mocked_home / "home"
    with pytest.raises(
        FileNotFoundError, match=f"No .fmu directory found at {user_home}"
    ):
        UserFMUDirectory()

    response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
    assert response.status_code == status.HTTP_200_OK, response.json()
    # Does not raise
    user_fmu_dir = UserFMUDirectory()
    assert response.json() == {"message": "Session created"}
    assert user_fmu_dir.path == user_home / ".fmu"


async def test_get_session_creates_session(
    tmp_path_mocked_home: Path,
    mock_token: str,
    session_manager: SessionManager,
) -> None:
    """Tests that user .fmu is created when a session is created."""
    client = TestClient(app)
    user_home = tmp_path_mocked_home / "home"
    response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
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
    client = TestClient(app)
    user_fmu_dir = init_user_fmu_directory()

    response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
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
    client = TestClient(app)
    user_fmu_dir = init_user_fmu_directory()
    project_fmu_dir = init_fmu_directory(tmp_path_mocked_home)
    ert_model_path = tmp_path_mocked_home / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
    assert response.status_code == status.HTTP_200_OK, response.json()
    # Does not raise
    user_fmu_dir = UserFMUDirectory()
    assert response.json() == {"message": "Session created"}
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


async def test_getting_two_sessions_destroys_existing_session(
    tmp_path_mocked_home: Path,
    mock_token: str,
    session_manager: SessionManager,
) -> None:
    """Tests that creating a new session destroys the old, if it exists."""
    client = TestClient(app)
    user_home = tmp_path_mocked_home / "home"
    response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
    assert response.status_code == status.HTTP_200_OK, response.json()

    user_fmu_dir = UserFMUDirectory()
    assert user_fmu_dir.path == user_home / ".fmu"

    session_id = response.cookies.get(settings.SESSION_COOKIE_KEY)
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert session is not None
    assert isinstance(session, Session)
    assert session.user_fmu_directory.path == user_fmu_dir.path

    # New session
    response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
    assert response.status_code == status.HTTP_200_OK, response.json()

    new_session_id = response.cookies.get(settings.SESSION_COOKIE_KEY)
    assert new_session_id is not None
    new_session = await session_manager.get_session(new_session_id)
    assert new_session is not None
    assert isinstance(new_session, Session)
    assert new_session.user_fmu_directory.path == user_fmu_dir.path

    # Ensure not same and destroyed
    assert session_id != new_session_id
    with pytest.raises(SessionNotFoundError, match="No active session found"):
        await session_manager.get_session(session_id)


async def test_session_creation_handles_lock_conflicts(
    tmp_path_mocked_home: Path,
    mock_token: str,
    session_manager: SessionManager,
    monkeypatch: MonkeyPatch,
) -> None:
    """Tests that session creation handles lock conflicts gracefully."""
    client = TestClient(app)

    project_path = tmp_path_mocked_home / "test_project"
    project_path.mkdir()
    init_fmu_directory(project_path)
    monkeypatch.chdir(project_path)

    with patch(
        "fmu_settings_api.v1.routes.session.add_fmu_project_to_session",
        side_effect=LockError("Project is locked by another process"),
    ):
        response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "Session created"}

        session_id = response.cookies.get(settings.SESSION_COOKIE_KEY)
        assert session_id is not None

        session = await session_manager.get_session(session_id)
        assert session is not None

        assert isinstance(session, Session)
        assert not hasattr(session, "project_fmu_directory")


def test_patch_invalid_access_token_key_to_session(
    client_with_session: TestClient,
) -> None:
    """Tests that submitting an unsupported access token/scope does return 400."""
    response = client_with_session.patch(
        f"{ROUTE}/access_token",
        json={
            "id": "foo",
            "key": "secret",
        },
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "Access token id foo is not known or supported"


async def test_patch_access_token_to_user_fmu_session(
    client_with_session: TestClient,
) -> None:
    """Tests that submitting a valid access token key pair is saved to the session."""
    session_id = client_with_session.cookies.get(settings.SESSION_COOKIE_KEY, None)
    assert session_id is not None

    from fmu_settings_api.session import session_manager  # noqa: PLC0415

    session = await session_manager.get_session(session_id)
    assert session is not None
    assert session.access_tokens.smda_api is None

    response = client_with_session.patch(
        f"{ROUTE}/access_token",
        json={
            "id": "smda_api",
            "key": "secret",
        },
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["message"] == "Set session access token for smda_api"

    session = await session_manager.get_session(session_id)
    assert session.access_tokens.smda_api == SecretStr("secret")


async def test_patch_access_token_unknown_failure(
    client_with_session: TestClient,
) -> None:
    """Tests that an unknown exception returns 500."""
    with patch(
        "fmu_settings_api.v1.routes.session.add_access_token_to_session",
        side_effect=Exception("foo"),
    ):
        session_id = client_with_session.cookies.get(settings.SESSION_COOKIE_KEY, None)
        assert session_id is not None

        from fmu_settings_api.session import session_manager  # noqa: PLC0415

        session = await session_manager.get_session(session_id)
        assert session is not None
        assert session.access_tokens.smda_api is None

        response = client_with_session.patch(
            f"{ROUTE}/access_token",
            json={
                "id": "smda_api",
                "key": "secret",
            },
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json()["detail"] == "foo"


def test_post_session_handles_general_exception(
    tmp_path_mocked_home: Path, mock_token: str
) -> None:
    """Tests that session creation handles general exceptions properly."""
    client = TestClient(app)

    with patch(
        "fmu_settings_api.v1.routes.session.create_fmu_session",
        side_effect=RuntimeError("Session creation failed"),
    ):
        response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Session creation failed" in response.json()["detail"]
