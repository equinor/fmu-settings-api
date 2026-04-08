"""Tests the /api/v1/session routes."""

import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

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
    RmsSession,
    Session,
    SessionManager,
    SessionNotFoundError,
    add_rms_project_to_session,
    destroy_fmu_session_if_expired,
    get_fmu_session,
    update_fmu_session,
)

ROUTE = "/api/v1/session"


# POST session/ #


def test_post_session_no_token() -> None:
    """Tests the fmu routes require a session."""
    client = TestClient(app)
    response = client.post(ROUTE)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
    assert response.json() == {"detail": "Not authenticated"}


def test_post_session_invalid_token() -> None:
    """Tests the fmu routes require a session."""
    client = TestClient(app)
    bad_token = "no" * 32
    response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: bad_token})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "Not authorized"}


def test_post_session_no_token_does_not_create_user_fmu(
    tmp_path_mocked_home: Path,
) -> None:
    """Tests unauthenticated requests do not create a user .fmu."""
    client = TestClient(app)
    response = client.post(ROUTE)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "Not authenticated"}
    assert not (tmp_path_mocked_home / "home/.fmu").exists()


def test_post_session_invalid_token_does_not_create_user_fmu(
    tmp_path_mocked_home: Path,
) -> None:
    """Tests unauthorized requests do not create a user .fmu."""
    client = TestClient(app)
    bad_token = "no" * 32
    response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: bad_token})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "Not authorized"}
    assert not (tmp_path_mocked_home / "home/.fmu").exists()


def test_post_session_create_user_fmu_no_permissions(
    user_fmu_dir_no_permissions: Path, mock_token: str
) -> None:
    """Tests that user .fmu directory permissions errors return a 403."""
    client = TestClient(app)
    response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Permission denied creating user .fmu"}


def test_post_session_creating_user_fmu_exists_as_a_file(
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


def test_post_session_creating_user_unknown_failure(
    tmp_path_mocked_home: Path, mock_token: str, monkeypatch: MonkeyPatch
) -> None:
    """Tests that an unknown exception returns 500."""
    client = TestClient(app)
    with patch(
        "fmu_settings_api.deps.user_fmu.init_user_fmu_directory",
        side_effect=Exception("foo"),
    ):
        user_fmu_path = tmp_path_mocked_home / "home/.fmu"
        assert not user_fmu_path.exists()

        monkeypatch.chdir(tmp_path_mocked_home)
        init_fmu_directory(tmp_path_mocked_home)
        response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


async def test_post_session_creates_session_and_user_fmu(
    tmp_path_mocked_home: Path,
    mock_token: str,
    session_manager: SessionManager,
) -> None:
    """Tests that a session and user .fmu is created when posting a session."""
    client = TestClient(app)
    user_home = tmp_path_mocked_home / "home"
    with pytest.raises(
        FileNotFoundError, match=f"No .fmu directory found at {user_home}"
    ):
        UserFMUDirectory()

    response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
    assert response.status_code == status.HTTP_200_OK, response.json()

    # Assert session has been created
    session_id = response.cookies.get(settings.SESSION_COOKIE_KEY)
    assert session_id is not None
    session = await get_fmu_session(session_id)
    assert isinstance(session, Session)

    # Assert user fmu has been created and opened in the session
    user_fmu_dir = UserFMUDirectory()
    assert user_fmu_dir.path == user_home / ".fmu"
    assert session.user_fmu_directory.path == user_fmu_dir.path
    assert session.user_fmu_directory.config.load() == user_fmu_dir.config.load()


async def test_post_session_finds_existing_user_fmu(
    tmp_path_mocked_home: Path,
    mock_token: str,
    session_manager: SessionManager,
) -> None:
    """Tests that an existing user .fmu directory is located when posting a session."""
    client = TestClient(app)
    user_fmu_dir = init_user_fmu_directory()

    response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
    assert response.status_code == status.HTTP_200_OK, response.json()

    session_id = response.cookies.get(settings.SESSION_COOKIE_KEY)
    assert session_id is not None

    session = await get_fmu_session(session_id)
    assert session is not None

    assert isinstance(session, Session)
    assert session.user_fmu_directory.path == user_fmu_dir.path


async def test_post_session_from_project_path_returns_fmu_project(
    tmp_path_mocked_home: Path,
    mock_token: str,
    monkeypatch: MonkeyPatch,
    session_manager: SessionManager,
) -> None:
    """Tests that project session is created when posting session from project path."""
    client = TestClient(app)
    initial_user_fmu_dir = init_user_fmu_directory()
    project_fmu_dir = init_fmu_directory(tmp_path_mocked_home)
    ert_model_path = tmp_path_mocked_home / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
    assert response.status_code == status.HTTP_200_OK, response.json()
    # Does not raise
    user_fmu_dir = UserFMUDirectory()
    payload = response.json()

    session_id = response.cookies.get(settings.SESSION_COOKIE_KEY)
    assert session_id is not None
    assert payload["id"] == session_id
    assert "created_at" in payload
    assert "expires_at" in payload
    assert "last_accessed" in payload
    assert user_fmu_dir.path == initial_user_fmu_dir.path

    session = await get_fmu_session(session_id)
    assert session is not None
    assert isinstance(session, ProjectSession)

    assert session.user_fmu_directory.path == user_fmu_dir.path
    assert session.user_fmu_directory.config.load() == user_fmu_dir.config.load()

    assert session.project_fmu_directory.path == project_fmu_dir.path
    assert session.project_fmu_directory.config.load() == project_fmu_dir.config.load()


async def test_post_session_destroy_existing_expired_session(
    tmp_path_mocked_home: Path,
    mock_token: str,
    session_manager: SessionManager,
) -> None:
    """Tests creating a new session destroys the old expired session before creation.

    Scenario: A session with the session_id provided already exists, but is expired.
    The existing expired session should be destroyed before a new session is created.
    """
    client = TestClient(app)
    response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
    assert response.status_code == status.HTTP_200_OK, response.json()

    session_id = response.cookies.get(settings.SESSION_COOKIE_KEY)
    assert session_id is not None
    session = await get_fmu_session(session_id)
    assert session.id == session_id
    assert isinstance(session, Session)

    # Expire the session
    expired_timestamp = datetime.now(UTC)
    session.expires_at = expired_timestamp
    await update_fmu_session(session)

    # Post new session and assert that the expired session is removed first
    with patch(
        "fmu_settings_api.deps.session.destroy_fmu_session_if_expired",
        new_callable=AsyncMock,
        wraps=destroy_fmu_session_if_expired,
    ) as mock_destroy_session:
        response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
        assert response.status_code == status.HTTP_200_OK, response.json()
        mock_destroy_session.assert_awaited_once_with(session_id)

    new_session_id = response.cookies.get(settings.SESSION_COOKIE_KEY)

    assert new_session_id is not None
    assert new_session_id != session_id
    with pytest.raises(SessionNotFoundError, match="No active session found"):
        await get_fmu_session(session_id)

    new_session = await get_fmu_session(new_session_id)
    assert new_session is not None
    assert isinstance(new_session, Session)
    assert new_session.expires_at > expired_timestamp


async def test_post_session_renews_existing_valid_session(
    tmp_path_mocked_home: Path,
    client_with_session: TestClient,
    session_manager: SessionManager,
    mock_token: str,
) -> None:
    """Tests POSTing to session renews an existing valid user session.

    Scenario: A valid user session with the session_id provided already exists.
    The existing session should be renewed with a new session id and expiry
    while keeping the current session state.
    """
    client = TestClient(app)
    response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
    assert response.status_code == status.HTTP_200_OK, response.json()

    session_id = response.cookies.get(settings.SESSION_COOKIE_KEY)
    assert session_id is not None
    session = await get_fmu_session(session_id)
    assert session.id == session_id
    assert isinstance(session, Session)
    original_created_at = session.created_at
    original_expires_at = session.expires_at

    response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
    assert response.status_code == status.HTTP_200_OK

    renewed_session_id = response.cookies.get(settings.SESSION_COOKIE_KEY)
    assert renewed_session_id is not None
    assert renewed_session_id != session_id

    with pytest.raises(SessionNotFoundError, match="No active session found"):
        await get_fmu_session(session_id)

    renewed_session = await get_fmu_session(renewed_session_id)
    assert isinstance(renewed_session, Session)
    assert renewed_session.id == renewed_session_id
    assert renewed_session.user_fmu_directory.path == session.user_fmu_directory.path
    assert renewed_session.access_tokens == session.access_tokens
    assert renewed_session.created_at > original_created_at
    assert renewed_session.expires_at > original_expires_at


async def test_post_session_renews_existing_project_session(  # noqa: PLR0913
    tmp_path_mocked_home: Path,
    client_with_session: TestClient,
    session_manager: SessionManager,
    mock_token: str,
    monkeypatch: MonkeyPatch,
    make_fmu_project_root: Callable[[Path], Path],
) -> None:
    """Tests POSTing to session renews an existing project session.

    Scenario: A valid project session with the session_id provided already
    exists. The session should be renewed with a new session id while keeping
    the attached project, access tokens, and RMS session unchanged even if the
    current working directory changes.
    """
    project_path = tmp_path_mocked_home / "test_project"
    make_fmu_project_root(project_path)
    init_fmu_directory(project_path)
    monkeypatch.chdir(project_path)

    # Create new session with project and RMS session
    client = TestClient(app)
    response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
    assert response.status_code == status.HTTP_200_OK, response.json()
    session_id = response.cookies.get(settings.SESSION_COOKIE_KEY)
    assert session_id is not None
    session = await get_fmu_session(session_id)
    assert session.id == session_id
    assert isinstance(session, ProjectSession)

    original_created_at = session.created_at
    original_expires_at = session.expires_at

    with (
        patch(
            "fmu_settings_api.v1.routes.session.create_fmu_session",
            new_callable=AsyncMock,
        ) as mock_create_session,
        patch(
            "fmu_settings_api.v1.routes.session.add_fmu_project_to_session",
            new_callable=AsyncMock,
        ) as mock_add_project_to_session,
    ):
        client.patch(
            f"{ROUTE}/access_token",
            json={"id": "smda_api", "key": "secret_token"},
        )

        rms_executor = MagicMock(shutdown=MagicMock())
        rms_project = MagicMock(close=MagicMock())
        await add_rms_project_to_session(session_id, rms_executor, rms_project)

        updated_session = cast("ProjectSession", await get_fmu_session(session_id))
        assert updated_session.rms_session is not None
        assert updated_session.rms_session == RmsSession(
            rms_executor, rms_project, updated_session.rms_session.expires_at
        )

        different_path = tmp_path_mocked_home / "different_project"
        different_path.mkdir()
        monkeypatch.chdir(different_path)

        response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
        assert response.status_code == status.HTTP_200_OK
        mock_create_session.assert_not_awaited()
        mock_add_project_to_session.assert_not_awaited()

    renewed_session_id = response.cookies.get(settings.SESSION_COOKIE_KEY)
    assert renewed_session_id is not None
    assert renewed_session_id != session_id

    with pytest.raises(SessionNotFoundError, match="No active session found"):
        await get_fmu_session(session_id)

    renewed_session = cast("ProjectSession", await get_fmu_session(renewed_session_id))
    assert isinstance(renewed_session, ProjectSession)
    assert (
        renewed_session.project_fmu_directory.path == session.project_fmu_directory.path
    )
    assert renewed_session.access_tokens.smda_api is not None
    assert renewed_session.rms_session is not None
    assert renewed_session.rms_session.executor is rms_executor
    assert renewed_session.rms_session.project is rms_project
    assert renewed_session.created_at > original_created_at
    assert renewed_session.expires_at > original_expires_at


async def test_post_session_handles_lock_conflicts(
    tmp_path_mocked_home: Path,
    mock_token: str,
    session_manager: SessionManager,
    monkeypatch: MonkeyPatch,
    make_fmu_project_root: Callable[[Path], Path],
) -> None:
    """Tests that session creation handles lock conflicts gracefully."""
    client = TestClient(app)

    project_path = tmp_path_mocked_home / "test_project"
    make_fmu_project_root(project_path)
    init_fmu_directory(project_path)
    monkeypatch.chdir(project_path)

    with patch(
        "fmu_settings_api.v1.routes.session.add_fmu_project_to_session",
        side_effect=LockError("Project is locked by another process"),
    ):
        response = client.post(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        assert "id" in payload
        assert "created_at" in payload
        assert "expires_at" in payload
        assert "last_accessed" in payload

        session_id = response.cookies.get(settings.SESSION_COOKIE_KEY)
        assert session_id is not None

        session = await get_fmu_session(session_id)
        assert session is not None

        assert isinstance(session, Session)
        assert not hasattr(session, "project_fmu_directory")


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
        assert response.json()["detail"] == "An unexpected error occurred."


# GET session/ #


async def test_get_session_returns_sanitised_payload(
    client_with_session: TestClient,
    session_manager: SessionManager,
) -> None:
    """Tests that GET /session returns the expected session snapshot."""
    response = client_with_session.get(ROUTE)
    assert response.status_code == status.HTTP_200_OK

    payload = response.json()
    session_id = client_with_session.cookies.get(settings.SESSION_COOKIE_KEY)
    assert session_id is not None
    session = await get_fmu_session(session_id)

    assert payload["id"] == session.id
    assert "user_fmu_directory" not in payload
    assert "access_tokens" not in payload


async def test_get_session_destroys_expired_session(
    client_with_session: TestClient,
    session_manager: SessionManager,
) -> None:
    """Tests that get session destroys session when it has expired."""
    session_id = client_with_session.cookies.get(settings.SESSION_COOKIE_KEY)
    assert session_id is not None

    # Expire session
    session = await get_fmu_session(session_id)
    session.expires_at = datetime.now(UTC)
    await update_fmu_session(session)

    response = client_with_session.get(ROUTE)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "No active session found"
    with pytest.raises(SessionNotFoundError):
        session = await get_fmu_session(session_id)


def test_get_session_requires_cookie() -> None:
    """Tests that a missing session cookie returns 401."""
    client = TestClient(app)
    response = client.get(ROUTE)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "No active session found"


def test_get_session_unknown_failure(client_with_session: TestClient) -> None:
    """Tests that an unexpected error when building the session response returns 500."""
    with patch(
        "fmu_settings_api.services.session.SessionResponse",
        side_effect=Exception("boom"),
    ):
        response = client_with_session.get(ROUTE)
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json()["detail"] == "An unexpected error occurred."


# PATCH session/access_token #


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

    session = await get_fmu_session(session_id)
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

    session = await get_fmu_session(session_id)
    assert session.access_tokens.smda_api == SecretStr("secret")


async def test_patch_access_token_unknown_failure(
    client_with_session: TestClient,
) -> None:
    """Tests that an unknown exception returns 500."""
    with patch(
        "fmu_settings_api.services.session.add_token_to_session_manager",
        side_effect=Exception("foo"),
    ):
        session_id = client_with_session.cookies.get(settings.SESSION_COOKIE_KEY, None)
        assert session_id is not None

        session = await get_fmu_session(session_id)
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
        assert response.json()["detail"] == "An unexpected error occurred."


async def test_post_restore_session_restores_user_fmu_directory(
    client_with_session: TestClient,
    session_manager: SessionManager,
) -> None:
    """Tests POST /session/restore recovers a deleted user .fmu directory."""
    session_id = client_with_session.cookies.get(settings.SESSION_COOKIE_KEY)
    assert session_id is not None

    session = await session_manager.get_session(session_id)
    user_fmu_path = session.user_fmu_directory.path
    assert user_fmu_path.exists()

    shutil.rmtree(user_fmu_path)
    assert not user_fmu_path.exists()

    response = client_with_session.post(f"{ROUTE}/restore")
    assert response.status_code == status.HTTP_200_OK, response.json()
    assert response.json()["message"] == "Restored .fmu resources"
    assert user_fmu_path.exists()
    assert session.user_fmu_directory.config.path.exists()


async def test_post_restore_session_restores_project_fmu_directory(
    client_with_project_session: TestClient,
    session_manager: SessionManager,
) -> None:
    """Tests POST /session/restore recovers a deleted project .fmu directory."""
    session_id = client_with_project_session.cookies.get(settings.SESSION_COOKIE_KEY)
    assert session_id is not None

    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    user_fmu_path = session.user_fmu_directory.path
    project_fmu_path = session.project_fmu_directory.path
    assert user_fmu_path.exists()
    assert project_fmu_path.exists()

    shutil.rmtree(project_fmu_path)
    assert not project_fmu_path.exists()

    response = client_with_project_session.post(f"{ROUTE}/restore")
    assert response.status_code == status.HTTP_200_OK, response.json()
    assert response.json()["message"] == "Restored .fmu resources"
    assert project_fmu_path.exists()
    assert session.project_fmu_directory.config.path.exists()


def test_post_restore_session_returns_lock_conflict_for_project(
    client_with_project_session: TestClient,
) -> None:
    """Tests POST /session/restore returns 423 on project lock conflicts."""
    error = (
        "Cannot write to .fmu directory because it is locked by "
        "someone@somehost (PID: 1234). Lock expires at Mon Jan  1 00:00:00 2030."
    )
    with patch(
        "fmu_settings_api.services.session.SessionService.restore_fmu_directories",
        side_effect=PermissionError(error),
    ):
        response = client_with_project_session.post(f"{ROUTE}/restore")

    assert response.status_code == status.HTTP_423_LOCKED, response.json()
    assert response.json()["detail"] == f"Project lock conflict: {error}"


def test_post_restore_session_returns_permission_denied(
    client_with_session: TestClient,
) -> None:
    """Tests POST /session/restore returns 403 on permission issues."""
    with patch(
        "fmu_settings_api.services.session.SessionService.restore_fmu_directories",
        side_effect=PermissionError("Permission denied"),
    ):
        response = client_with_session.post(f"{ROUTE}/restore")

    assert response.status_code == status.HTTP_403_FORBIDDEN, response.json()
    assert response.json()["detail"] == "Permission denied recovering .fmu resources"


def test_post_restore_session_returns_conflict(
    client_with_session: TestClient,
) -> None:
    """Tests POST /session/restore returns 409 when .fmu is not a directory."""
    error = ".fmu exists at /tmp/example but is not a directory"
    with patch(
        "fmu_settings_api.services.session.SessionService.restore_fmu_directories",
        side_effect=FileExistsError(error),
    ):
        response = client_with_session.post(f"{ROUTE}/restore")

    assert response.status_code == status.HTTP_409_CONFLICT, response.json()
    assert response.json()["detail"] == error
