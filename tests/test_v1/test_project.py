"""Tests the /api/v1/project routes."""

import json
import os
import shutil
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from fmu.datamodels.common import Access, Smda
from fmu.datamodels.fmu_results.fields import Model
from fmu.settings._fmu_dir import (
    ProjectFMUDirectory,
    UserFMUDirectory,
)
from fmu.settings._global_config import InvalidGlobalConfigurationError
from fmu.settings._init import init_fmu_directory
from fmu.settings.models.mappings import Mappings
from pytest import MonkeyPatch

from fmu_settings_api.__main__ import app
from fmu_settings_api.config import HttpHeader, settings
from fmu_settings_api.models.project import FMUProject
from fmu_settings_api.session import (
    ProjectSession,
    Session,
    SessionManager,
    SessionNotFoundError,
)
from fmu_settings_api.v1.routes.project import _create_opened_project_response

client = TestClient(app)

ROUTE = "/api/v1/project"


# GET project/ #


async def test_get_project_does_not_care_about_token(mock_token: str) -> None:
    """Tests that a header token is irrelevent to the route."""
    response = client.get(ROUTE)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "No active session found"}

    response = client.get(ROUTE, headers={HttpHeader.API_TOKEN_KEY: mock_token})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "No active session found"}

    response = client.get(ROUTE, headers={HttpHeader.API_TOKEN_KEY: "no" * 32})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "No active session found"}


async def test_get_project_no_directory_permissions(
    client_with_session: TestClient,
    session_tmp_path: Path,
    monkeypatch: MonkeyPatch,
    no_permissions: Callable[[str | Path], AbstractContextManager[None]],
) -> None:
    """Test 403 returns when lacking permissions somewhere in the path tree."""
    bad_project_dir = session_tmp_path / ".fmu"
    bad_project_dir.mkdir()

    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    with no_permissions(bad_project_dir):
        response = client_with_session.get(ROUTE)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Permission denied locating .fmu"}


async def test_get_project_directory_does_not_exist(
    client_with_session: TestClient, session_tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Test 404 returns when project .fmu cannot be found."""
    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    response = client_with_session.get(ROUTE)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {
        "detail": f"No .fmu directory found from {ert_model_path}"
    }


async def test_get_project_directory_is_not_directory(
    client_with_session: TestClient, session_tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Test 404 returns when project .fmu exists but is not a directory.

    Although a .fmu file exists, because a .fmu _directory_ is not, it is
    treated as a 404.
    """
    fmu_dir_path = session_tmp_path / ".fmu"
    fmu_dir_path.touch()
    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    response = client_with_session.get(ROUTE)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {
        "detail": f"No .fmu directory found from {ert_model_path}"
    }


async def test_get_project_session_not_found_error(
    client_with_session: TestClient, session_tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Test 401 returns when SessionNotFoundError is raised in get_project."""
    monkeypatch.chdir(session_tmp_path)
    init_fmu_directory(session_tmp_path)

    with patch(
        "fmu_settings_api.services.session.add_fmu_project_to_session",
        side_effect=SessionNotFoundError("Session not found"),
    ):
        response = client_with_session.get(ROUTE)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json() == {"detail": "Session not found"}


async def test_get_project_permission_error(
    client_with_session: TestClient,
) -> None:
    """Test 403 returns when PermissionError occurs in get_project."""
    # Mock find_nearest_fmu_directory to raise PermissionError
    with patch(
        "fmu_settings_api.services.session.find_nearest_fmu_directory",
        side_effect=PermissionError("Permission denied"),
    ):
        response = client_with_session.get(ROUTE)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json() == {"detail": "Permission denied locating .fmu"}


async def test_get_project_raises_other_exceptions(
    client_with_session: TestClient,
) -> None:
    """Test 500 returns if other exceptions are raised."""
    with patch(
        "fmu_settings_api.services.session.find_nearest_fmu_directory",
        side_effect=Exception("foo"),
    ):
        response = client_with_session.get(ROUTE)
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "An unexpected error occurred."}


async def test_get_project_directory_config_missing(
    client_with_session: TestClient, session_tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Test 404 returns when project .fmu has missing config."""
    monkeypatch.chdir(session_tmp_path)

    fmu_dir = init_fmu_directory(session_tmp_path)
    assert fmu_dir.config.exists

    fmu_dir.config.path.unlink()
    assert not fmu_dir.config.exists

    response = client_with_session.get(ROUTE)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"].startswith(
        f"Missing configuration file in project at {session_tmp_path}"
    )


async def test_get_project_directory_corrupt(
    client_with_session: TestClient, session_tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Test 500 returns when project .fmu has invalid config."""
    monkeypatch.chdir(session_tmp_path)

    fmu_dir = init_fmu_directory(session_tmp_path)
    with open(fmu_dir.config.path, "w") as f:
        f.write("incorrect")

    response = client_with_session.get(ROUTE)
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = response.json()["detail"]
    assert detail == "An unexpected error occurred."


async def test_get_project_directory_exists(
    client_with_session: TestClient,
    session_tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test 200 and config returns when .fmu exists."""
    existing_fmu_dir = init_fmu_directory(session_tmp_path)

    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    response = client_with_session.get(ROUTE)
    assert response.status_code == status.HTTP_200_OK, response.json()

    fmu_project = FMUProject.model_validate(response.json())
    assert fmu_project.path == session_tmp_path
    assert fmu_project.project_dir_name == session_tmp_path.name
    assert existing_fmu_dir.config.load() == fmu_project.config


async def test_get_project_writes_to_user_recent_projects(
    client_with_session: TestClient, session_tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Test 200 adds project to user's recent projects."""
    monkeypatch.chdir(session_tmp_path)
    init_fmu_directory(session_tmp_path)

    user_dir = UserFMUDirectory()
    assert user_dir.get_config_value("recent_project_directories") == []

    response = client_with_session.get(ROUTE)
    assert response.status_code == status.HTTP_200_OK

    user_dir = UserFMUDirectory()
    assert user_dir.get_config_value("recent_project_directories") == [session_tmp_path]


async def test_get_project_updates_session(
    client_with_session: TestClient,
    session_tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Tests that getting an project FMU directory updates the user session."""
    existing_fmu_dir = init_fmu_directory(session_tmp_path)

    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    response = client_with_session.get(ROUTE)
    assert response.status_code == status.HTTP_200_OK, response.json()

    session_id = client_with_session.cookies.get(settings.SESSION_COOKIE_KEY, None)
    assert session_id is not None

    from fmu_settings_api.session import session_manager  # noqa: PLC0415

    session = await session_manager.get_session(session_id)
    assert session is not None
    assert isinstance(session, ProjectSession)
    assert session.project_fmu_directory.path == session_tmp_path / ".fmu"
    assert existing_fmu_dir.config.load() == session.project_fmu_directory.config.load()


async def test_get_project_already_in_session(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Tests when an .fmu project is already in a session.

    It should just return that project .fmu instance in the session.
    """
    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    response = client_with_project_session.get(ROUTE)
    assert response.status_code == status.HTTP_200_OK, response.json()
    fmu_project = FMUProject.model_validate(response.json())

    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None

    from fmu_settings_api.session import session_manager  # noqa: PLC0415

    session = await session_manager.get_session(session_id)
    assert session is not None
    assert isinstance(session, ProjectSession)
    assert session.project_fmu_directory.path == session_tmp_path / ".fmu"
    assert session.project_fmu_directory.config.load() == fmu_project.config


# POST project/ #


async def test_post_fmu_directory_no_permissions(
    client_with_session: TestClient,
    session_tmp_path: Path,
    no_permissions: Callable[[str | Path], AbstractContextManager[None]],
) -> None:
    """Test 403 returns when lacking permissions to path."""
    bad_project_dir = session_tmp_path / ".fmu"
    bad_project_dir.mkdir()

    with no_permissions(bad_project_dir):
        response = client_with_session.post(ROUTE, json={"path": str(bad_project_dir)})
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {
        "detail": f"Permission denied accessing .fmu at {bad_project_dir}"
    }


async def test_post_fmu_directory_does_not_exist(
    client_with_session: TestClient,
) -> None:
    """Test 404 returns when .fmu or directory does not exist."""
    path = "/dev/null"
    response = client_with_session.post(ROUTE, json={"path": path})
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": f"No .fmu directory found at {path}"}


async def test_post_fmu_directory_is_not_directory(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 409 returns when .fmu exists but is not a directory."""
    path = session_tmp_path / ".fmu"
    path.touch()

    response = client_with_session.post(ROUTE, json={"path": str(session_tmp_path)})
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {
        "detail": f".fmu exists at {session_tmp_path} but is not a directory"
    }


async def test_post_project_directory_config_missing(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 404 returns when project .fmu has missing config."""
    fmu_dir = init_fmu_directory(session_tmp_path)
    assert fmu_dir.config.exists

    fmu_dir.config.path.unlink()
    assert not fmu_dir.config.exists

    response = client_with_session.post(ROUTE, json={"path": str(session_tmp_path)})
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"].startswith(
        f"Missing configuration file in project at {session_tmp_path}"
    )


async def test_post_project_directory_corrupt(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 500 returns when project .fmu has invalid config."""
    fmu_dir = init_fmu_directory(session_tmp_path)
    with open(fmu_dir.config.path, "w") as f:
        f.write("incorrect")

    response = client_with_session.post(ROUTE, json={"path": str(session_tmp_path)})
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = response.json()["detail"]
    assert detail == "An unexpected error occurred."


async def test_post_project_directory_not_exists(
    client_with_session: TestClient,
) -> None:
    """Test 404 returns with proper message when path does not exists."""
    path = Path("/non/existing/path")
    response = client_with_session.post(ROUTE, json={"path": str(path)})
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == f"Path {path} does not exist"


async def test_post_fmu_directory_session_not_found_error(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 401 returns when SessionNotFoundError is raised in post_project."""
    init_fmu_directory(session_tmp_path)

    with patch(
        "fmu_settings_api.services.session.add_fmu_project_to_session",
        side_effect=SessionNotFoundError("Session not found"),
    ):
        response = client_with_session.post(ROUTE, json={"path": str(session_tmp_path)})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json() == {"detail": "Session not found"}


async def test_post_fmu_directory_raises_other_exceptions(
    client_with_session: TestClient,
) -> None:
    """Test 500 returns if other exceptions are raised."""
    with patch(
        "fmu_settings_api.services.session.get_fmu_directory",
        side_effect=Exception("foo"),
    ):
        path = "/dev/null"
        response = client_with_session.post(ROUTE, json={"path": path})
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "An unexpected error occurred."}


async def test_post_project_writes_to_user_recent_projects(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 200 adds project to user's recent projects."""
    _fmu_dir = init_fmu_directory(session_tmp_path)

    user_dir = UserFMUDirectory()
    assert user_dir.get_config_value("recent_project_directories") == []

    response = client_with_session.post(ROUTE, json={"path": str(session_tmp_path)})
    assert response.status_code == status.HTTP_200_OK

    user_dir = UserFMUDirectory()
    assert user_dir.get_config_value("recent_project_directories") == [session_tmp_path]


async def test_post_project_removes_non_existing_from_user_recent_projects(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 404 removes a non-exsiting project from user's recent projects."""
    _fmu_dir = init_fmu_directory(session_tmp_path)

    non_existing_path = Path("/non/existing/path")

    user_dir = UserFMUDirectory()
    user_dir.set_config_value(
        "recent_project_directories", [session_tmp_path, non_existing_path]
    )

    from fmu_settings_api.session import session_manager  # noqa PLC0415

    # need to force a reload of the user config in the session
    session_id = client_with_session.cookies.get(settings.SESSION_COOKIE_KEY, None)
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    session.user_fmu_directory.config.load(force=True)

    response = client_with_session.post(ROUTE, json={"path": str(non_existing_path)})
    assert response.status_code == status.HTTP_404_NOT_FOUND

    user_dir = UserFMUDirectory()
    assert user_dir.get_config_value("recent_project_directories") == [session_tmp_path]


async def test_post_fmu_directory_exists(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 200 and config returns when .fmu exists.

    Also checks that the session instance is updated.
    """
    fmu_dir = init_fmu_directory(session_tmp_path)

    response = client_with_session.post(ROUTE, json={"path": str(session_tmp_path)})
    assert response.status_code == status.HTTP_200_OK
    fmu_project = FMUProject.model_validate(response.json())
    assert fmu_project.path == session_tmp_path
    assert fmu_project.project_dir_name == session_tmp_path.name
    assert fmu_dir.config.load() == fmu_project.config

    session_id = client_with_session.cookies.get(settings.SESSION_COOKIE_KEY, None)
    assert session_id is not None

    from fmu_settings_api.session import session_manager  # noqa: PLC0415

    session = await session_manager.get_session(session_id)
    assert session is not None
    assert isinstance(session, ProjectSession)
    assert session.project_fmu_directory.path == session_tmp_path / ".fmu"
    assert session.project_fmu_directory.config.load() == fmu_project.config


async def test_post_fmu_directory_changes_session_instance(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Tests that posting a new project changes the instance in the session."""
    project_x = session_tmp_path / "project_x"
    project_x.mkdir()
    x_fmu_dir = init_fmu_directory(project_x)

    project_y = session_tmp_path / "project_y"
    project_y.mkdir()
    y_fmu_dir = init_fmu_directory(project_y)

    # Check Project X
    response = client_with_session.post(ROUTE, json={"path": str(project_x)})
    assert response.status_code == status.HTTP_200_OK, response.json()
    fmu_project = FMUProject.model_validate(response.json())
    assert fmu_project.path == project_x
    assert fmu_project.project_dir_name == project_x.name
    assert x_fmu_dir.config.load() == fmu_project.config

    session_id = client_with_session.cookies.get(settings.SESSION_COOKIE_KEY, None)
    assert session_id is not None

    from fmu_settings_api.session import session_manager  # noqa: PLC0415

    session = await session_manager.get_session(session_id)
    assert session is not None
    assert isinstance(session, ProjectSession)
    assert session.project_fmu_directory.path == project_x / ".fmu"
    assert session.project_fmu_directory.config.load() == fmu_project.config

    # Check Project Y
    response = client_with_session.post(ROUTE, json={"path": str(project_y)})
    assert response.status_code == status.HTTP_200_OK, response.json()
    fmu_project = FMUProject.model_validate(response.json())
    assert fmu_project.path == project_y
    assert fmu_project.project_dir_name == project_y.name
    assert y_fmu_dir.config.load() == fmu_project.config

    session = await session_manager.get_session(session_id)
    assert session is not None
    assert isinstance(session, ProjectSession)
    assert session.project_fmu_directory.path == project_y / ".fmu"
    assert session.project_fmu_directory.config.load() == fmu_project.config


# DELETE project/ #


async def test_delete_project_session_requires_session(
    tmp_path_mocked_home: Path,
) -> None:
    """Tests that deleting a project session requires a user session."""
    response = client.delete(ROUTE)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
    assert response.json()["detail"] == "No active session found"


async def test_delete_project_session_requires_project_session(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Tests that deleting a project session requires a user session."""
    response = client_with_session.delete(ROUTE)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
    assert response.json()["detail"] == "No FMU project directory open"


async def test_delete_project_session_returns_to_user_session(
    client_with_project_session: TestClient, session_tmp_path: Path
) -> None:
    """Tests that deleting a project session returns to a user session."""
    from fmu_settings_api.session import session_manager  # noqa: PLC0415

    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert session is not None
    assert isinstance(session, ProjectSession)

    response = client_with_project_session.delete(ROUTE)
    assert response.status_code == status.HTTP_200_OK, response.json()
    assert (
        response.json()["message"]
        == f"FMU directory {session.project_fmu_directory.path} closed successfully"
    )
    deleted_session_id = response.cookies.get(settings.SESSION_COOKIE_KEY, None)
    assert deleted_session_id is None

    session = await session_manager.get_session(session_id)
    assert session is not None
    assert isinstance(session, Session)


async def test_delete_project_session_not_found_error(
    client_with_project_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 401 when SessionNotFoundError is raised in delete_project_session."""
    with patch(
        "fmu_settings_api.services.session.remove_fmu_project_from_session",
        side_effect=SessionNotFoundError("Session not found"),
    ):
        response = client_with_project_session.delete(ROUTE)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json() == {"detail": "Session not found"}


async def test_delete_project_session_other_exception(
    client_with_project_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 500 when other exceptions are raised in delete_project_session."""
    with patch(
        "fmu_settings_api.services.session.remove_fmu_project_from_session",
        side_effect=Exception("Unexpected error"),
    ):
        response = client_with_project_session.delete(ROUTE)
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "An unexpected error occurred."}


# POST project/init #


async def test_post_init_fmu_directory_no_permissions(
    client_with_session: TestClient,
    session_tmp_path: Path,
    no_permissions: Callable[[str | Path], AbstractContextManager[None]],
) -> None:
    """Test 403 returns when lacking permissions to path."""
    path = session_tmp_path / "foo"
    path.mkdir()

    with no_permissions(path):
        response = client_with_session.post(f"{ROUTE}/init", json={"path": str(path)})
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": f"Permission denied creating .fmu at {path}"}


async def test_post_init_fmu_directory_does_not_exist(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 404 returns when directory to initialize .fmu does not exist."""
    path = "/dev/null/foo"
    response = client_with_session.post(f"{ROUTE}/init", json={"path": path})
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": f"Path {path} does not exist"}


async def test_post_init_fmu_directory_is_not_a_directory(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 409 returns when .fmu exists as a file at a path."""
    path = session_tmp_path / ".fmu"
    path.touch()

    response = client_with_session.post(
        f"{ROUTE}/init", json={"path": str(session_tmp_path)}
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {"detail": f".fmu already exists at {session_tmp_path}"}


async def test_post_init_fmu_directory_already_exists(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 409 returns when .fmu exists already at a path."""
    path = session_tmp_path / ".fmu"
    path.mkdir()

    response = client_with_session.post(
        f"{ROUTE}/init", json={"path": str(session_tmp_path)}
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {"detail": f".fmu already exists at {session_tmp_path}"}


async def test_post_init_fmu_directory_session_not_found_error(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 401 returns when SessionNotFoundError is raised in init_project."""
    with patch(
        "fmu_settings_api.services.session.add_fmu_project_to_session",
        side_effect=SessionNotFoundError("Session not found"),
    ):
        response = client_with_session.post(
            f"{ROUTE}/init", json={"path": str(session_tmp_path)}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json() == {"detail": "Session not found"}


async def test_post_init_fmu_directory_raises_other_exceptions(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 500 returns if other exceptions are raised."""
    with patch(
        "fmu_settings_api.services.session.init_fmu_directory",
        side_effect=Exception("foo"),
    ):
        path = "/dev/null"
        response = client_with_session.post(f"{ROUTE}/init", json={"path": path})
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "An unexpected error occurred."}


async def test_post_init_and_get_fmu_directory_succeeds(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 200 and config returns when .fmu exists."""
    tmp_path = session_tmp_path
    init_response = client_with_session.post(
        f"{ROUTE}/init", json={"path": str(tmp_path)}
    )
    assert init_response.status_code == status.HTTP_200_OK
    init_fmu_project = FMUProject.model_validate(init_response.json())
    assert init_fmu_project.path == tmp_path
    assert init_fmu_project.project_dir_name == tmp_path.name

    assert (tmp_path / ".fmu").exists()
    assert (tmp_path / ".fmu").is_dir()
    assert (tmp_path / ".fmu/config.json").exists()

    get_response = client_with_session.post(ROUTE, json={"path": str(tmp_path)})
    assert get_response.status_code == status.HTTP_200_OK
    get_fmu_project = FMUProject.model_validate(get_response.json())
    assert init_fmu_project == get_fmu_project


async def test_post_init_updates_session_instance(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test thats a POST fmu/init succeeds and sets a session cookie."""
    init_response = client_with_session.post(
        f"{ROUTE}/init", json={"path": str(session_tmp_path)}
    )
    assert init_response.status_code == status.HTTP_200_OK
    session_id = client_with_session.cookies.get(settings.SESSION_COOKIE_KEY, None)
    assert session_id is not None

    from fmu_settings_api.session import session_manager  # noqa: PLC0415

    session = await session_manager.get_session(session_id)
    assert session is not None
    assert isinstance(session, ProjectSession)
    assert session.project_fmu_directory.path == session_tmp_path / ".fmu"
    assert session.user_fmu_directory.path == UserFMUDirectory().path


async def test_post_init_writes_to_user_recent_projects(
    client_with_session: TestClient, session_tmp_path: Path
) -> None:
    """Test 200 adds project to user's recent projects."""
    user_dir = UserFMUDirectory()
    assert user_dir.get_config_value("recent_project_directories") == []

    response = client_with_session.post(
        f"{ROUTE}/init", json={"path": str(session_tmp_path)}
    )
    assert response.status_code == status.HTTP_200_OK

    user_dir = UserFMUDirectory()
    assert user_dir.get_config_value("recent_project_directories") == [session_tmp_path]


# PATCH project/masterdata #


async def test_patch_masterdata_project(
    client_with_project_session: TestClient,
    smda_masterdata: dict[str, Any],
) -> None:
    """Test saving SMDA masterdata to project .fmu."""
    # Get project session and check that masterdata is not set
    get_response = client_with_project_session.get(ROUTE)
    get_fmu_project = FMUProject.model_validate(get_response.json())
    assert get_fmu_project.config.masterdata is None

    # Store masterdata to project
    response = client_with_project_session.patch(
        f"{ROUTE}/masterdata", json=smda_masterdata
    )
    assert response.status_code == status.HTTP_200_OK
    assert (
        response.json()["message"]
        == f"Saved SMDA masterdata to {get_fmu_project.path / '.fmu'}"
    )
    # Refetch the project to see that masterdata is set
    get_response = client_with_project_session.get(ROUTE)
    get_fmu_project = FMUProject.model_validate(get_response.json())
    assert get_fmu_project.config.masterdata is not None
    assert get_fmu_project.config.masterdata.smda == Smda.model_validate(
        smda_masterdata
    )
    assert get_fmu_project.config.masterdata.smda.field[0].identifier == "OseFax"


async def test_patch_masterdata_requires_project_session(
    client_with_session: TestClient,
    smda_masterdata: dict[str, Any],
) -> None:
    """Test saving SMDA masterdata to .fmu requires an active project."""
    response = client_with_session.patch(f"{ROUTE}/masterdata", json=smda_masterdata)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
    assert response.json()["detail"] == "No FMU project directory open"


async def test_patch_masterdata_no_directory_permissions(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
    smda_masterdata: dict[str, Any],
    no_permissions: Callable[[str | Path], AbstractContextManager[None]],
) -> None:
    """Test 403 returns when lacking permissions."""
    bad_project_dir = session_tmp_path / ".fmu"

    with no_permissions(bad_project_dir):
        response = client_with_project_session.patch(
            f"{ROUTE}/masterdata", json=smda_masterdata
        )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {
        "detail": f"Permission denied accessing .fmu at {bad_project_dir}"
    }


async def test_patch_masterdata_no_directory(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
    smda_masterdata: dict[str, Any],
) -> None:
    """Test that if .fmu/ is deleted during a session an error is raised."""
    project_dir = session_tmp_path / ".fmu"

    # remove project .fmu
    shutil.rmtree(project_dir)
    assert not project_dir.exists()

    response = client_with_project_session.patch(
        f"{ROUTE}/masterdata", json=smda_masterdata
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND, response.json()["detail"]


async def test_patch_masterdata_lockfile_removed(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
    smda_masterdata: dict[str, Any],
    session_manager: SessionManager,
) -> None:
    """Test that the lock-file is re-acquired if it was manually removed."""
    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    fmu_dir = session.project_fmu_directory

    assert fmu_dir._lock.exists
    # Lock file was manually deleted
    fmu_dir._lock.path.unlink()
    assert fmu_dir._lock.exists is False

    response = client_with_project_session.patch(
        f"{ROUTE}/masterdata", json=smda_masterdata
    )
    # Forbidden. Lock must be re-acquired.
    assert response.status_code == status.HTTP_423_LOCKED, response.json()
    assert "Project lock file is missing" in response.json()["detail"]


async def test_patch_masterdata_lockfile_removed_and_acquired_by_other(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
    smda_masterdata: dict[str, Any],
    session_manager: SessionManager,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test that the lock-file is re-acquired if it was manually removed."""
    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    fmu_dir = session.project_fmu_directory

    assert fmu_dir._lock.exists
    # Lock file was manually deleted
    fmu_dir._lock.path.unlink()
    assert fmu_dir._lock.exists is False

    # Other user acquires it
    cur_user = os.environ.get("USER", "good")
    monkeypatch.setenv("USER", "bad")
    bad_fmu_dir = ProjectFMUDirectory(fmu_dir.path.parent)
    with patch("os.getpid", return_value=-1234):
        bad_fmu_dir._lock.acquire()
    monkeypatch.setenv("USER", cur_user)
    assert bad_fmu_dir._lock.load(force=True, store_cache=False).user == "bad"
    assert fmu_dir._lock.load(force=True, store_cache=False).user == "bad"

    response = client_with_project_session.patch(
        f"{ROUTE}/masterdata", json=smda_masterdata
    )
    assert response.status_code == status.HTTP_423_LOCKED, response.json()


async def test_patch_masterdata_general_exception(
    client_with_project_session: TestClient,
    smda_masterdata: dict[str, Any],
    session_manager: SessionManager,
) -> None:
    """Test 500 returns when general exceptions occur in patch_masterdata."""
    # Get the project session to access its project_fmu_directory
    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    # Mock the project_fmu_directory.set_config_value to raise ValueError
    with patch.object(
        session.project_fmu_directory,
        "set_config_value",
        side_effect=ValueError("Invalid config value"),
    ):
        response = client_with_project_session.patch(
            f"{ROUTE}/masterdata", json=smda_masterdata
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "An unexpected error occurred."}


async def test_load_global_config_from_default_path(
    client_with_project_session: TestClient, global_config_default_path: Path
) -> None:
    """Test loading masterdata from the default global config path.

    When a valid global config file exists at the default path and
    no custom path is provided in the request, loading masterdata
    into the project masterdata should be sucessfull.
    """
    # Check that the global config exists at the default location
    assert global_config_default_path.exists()
    with open(global_config_default_path, encoding="utf-8") as f:
        global_config = json.loads(f.read())

    # Get project session and check that masterdata is not set
    get_response = client_with_project_session.get(ROUTE)
    fmu_project = FMUProject.model_validate(get_response.json())
    assert fmu_project.config.masterdata is None

    # Do the post request and check the response
    response = client_with_project_session.post(f"{ROUTE}/global_config")
    assert response.status_code == status.HTTP_200_OK
    assert (
        response.json()["message"]
        == "Global config masterdata was successfully loaded "
        "into the project masterdata."
    )

    # Get project data and check that masterdata has been set
    get_response = client_with_project_session.get(ROUTE)
    fmu_project = FMUProject.model_validate(get_response.json())
    expected_field_uuid = UUID(global_config["masterdata"]["smda"]["field"][0]["uuid"])
    expected_field_identifier = global_config["masterdata"]["smda"]["field"][0][
        "identifier"
    ]
    expected_smda_country = global_config["masterdata"]["smda"]["country"][0][
        "identifier"
    ]

    assert fmu_project.config.masterdata is not None
    assert fmu_project.config.masterdata.smda.field[0].uuid == expected_field_uuid
    assert (
        fmu_project.config.masterdata.smda.field[0].identifier
        == expected_field_identifier
    )
    assert (
        fmu_project.config.masterdata.smda.country[0].identifier
        == expected_smda_country
    )


async def test_load_global_config_from_custom_path(
    client_with_project_session: TestClient,
    tmp_path: Path,
    global_config_custom_path: Path,
) -> None:
    """Test loading masterdata from a custom path.

    When a valid global config file exists at the path
    provided in the request, loading masterdata into
    the project masterdata should be sucessfull.
    """
    # Check that the global config exists at the custom location
    assert global_config_custom_path.exists()
    with open(global_config_custom_path, encoding="utf-8") as f:
        global_config = json.loads(f.read())

    # Get project session and check that masterdata is not set
    get_response = client_with_project_session.get(ROUTE)
    fmu_project = FMUProject.model_validate(get_response.json())
    assert fmu_project.config.masterdata is None

    # Do the post request and check the response
    response = client_with_project_session.post(
        url=f"{ROUTE}/global_config",
        json={"relative_path": str(global_config_custom_path.relative_to(tmp_path))},
    )
    assert response.status_code == status.HTTP_200_OK
    assert (
        response.json()["message"]
        == "Global config masterdata was successfully loaded "
        "into the project masterdata."
    )

    # Get project data and check that masterdata has been set
    get_response = client_with_project_session.get(ROUTE)
    fmu_project = FMUProject.model_validate(get_response.json())
    expected_field_uuid = UUID(global_config["masterdata"]["smda"]["field"][0]["uuid"])
    expected_field_identifier = global_config["masterdata"]["smda"]["field"][0][
        "identifier"
    ]
    expected_smda_country = global_config["masterdata"]["smda"]["country"][0][
        "identifier"
    ]

    assert fmu_project.config.masterdata is not None
    assert fmu_project.config.masterdata.smda.field[0].uuid == expected_field_uuid
    assert (
        fmu_project.config.masterdata.smda.field[0].identifier
        == expected_field_identifier
    )
    assert (
        fmu_project.config.masterdata.smda.country[0].identifier
        == expected_smda_country
    )


async def test_load_global_config_default_file_not_found(
    client_with_project_session: TestClient, tmp_path: Path
) -> None:
    """Test 404 is returned when the default global config is not found."""
    response = client_with_project_session.post(f"{ROUTE}/global_config")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {
        "detail": "No valid global config file found in the project."
    }


async def test_load_global_config_provided_file_not_found(
    client_with_project_session: TestClient, tmp_path: Path
) -> None:
    """Test 404 is returned when the file at the provided path is not found."""
    custom_config_path = Path("custom/fmuconfig/output/global_variables.yml")
    response = client_with_project_session.post(
        f"{ROUTE}/global_config", json={"relative_path": str(custom_config_path)}
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {
        "detail": "No valid global config file found in the project."
    }


async def test_load_global_config_invalid_model(
    client_with_project_session: TestClient,
    global_config_default_path: Path,
) -> None:
    """Test 422 returned when the global config data is invalid."""
    # Make the global config invalid
    with open(global_config_default_path, encoding="utf-8") as f:
        global_config = json.loads(f.read())
    del global_config["masterdata"]
    with open(global_config_default_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(global_config, indent=2, sort_keys=True))

    response = client_with_project_session.post(f"{ROUTE}/global_config")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert (
        response.json()["detail"]["message"] == "The global config file is not valid."
    )
    assert "validation_errors" in response.json()["detail"]
    assert response.json()["detail"]["validation_errors"][0]["type"] == "missing"
    assert response.json()["detail"]["validation_errors"][0]["loc"][0] == "masterdata"
    assert response.json()["detail"]["validation_errors"][0]["msg"] == "Field required"


async def test_load_global_config_with_no_project_session(
    client_with_session: TestClient,
) -> None:
    """Test 401 returned when user does not have a project session."""
    response = client_with_session.post(f"{ROUTE}/global_config")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "No FMU project directory open"}


async def test_load_global_config_general_exception(
    client_with_project_session: TestClient,
    global_config_default_path: Path,
) -> None:
    """Test 500 returns when general exception occurs in post_global_config."""
    with patch(
        "fmu_settings_api.services.project.find_global_config",
        side_effect=RuntimeError("Config processing error"),
    ):
        response = client_with_project_session.post(f"{ROUTE}/global_config")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "An unexpected error occurred."}


async def test_load_global_config_existing_masterdata(
    client_with_project_session: TestClient,
    global_config_default_path: Path,
    smda_masterdata: dict[str, Any],
) -> None:
    """Test 409 returned when masterdata is already present in the project config."""
    assert global_config_default_path.exists()

    response = client_with_project_session.patch(
        f"{ROUTE}/masterdata", json=smda_masterdata
    )

    response = client_with_project_session.post(f"{ROUTE}/global_config")
    assert response.status_code == status.HTTP_409_CONFLICT
    assert "A config file with masterdata already exists in .fmu" in str(
        response.json()
    )


async def test_check_global_config_succeeds(
    client_with_project_session: TestClient, global_config_default_path: Path
) -> None:
    """Test 200 returned when a valid global config exists at the default location."""
    assert global_config_default_path.exists()
    response = client_with_project_session.get(f"{ROUTE}/global_config_status")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "ok"


async def test_check_global_config_not_found(
    client_with_project_session: TestClient, tmp_path: Path
) -> None:
    """Test 404 returned when no global config is found at the default location."""
    response = client_with_project_session.get(f"{ROUTE}/global_config_status")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {
        "detail": "No valid global config file found in the project."
    }


async def test_check_global_config_not_valid(
    client_with_project_session: TestClient, global_config_default_path: Path
) -> None:
    """Test 422 returned when the global config at the default location is invalid."""
    # Make the global config invalid
    with open(global_config_default_path, encoding="utf-8") as f:
        global_config = json.loads(f.read())
    del global_config["masterdata"]
    with open(global_config_default_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(global_config, indent=2, sort_keys=True))

    response = client_with_project_session.get(f"{ROUTE}/global_config_status")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert (
        response.json()["detail"]["message"] == "The global config file is not valid."
    )
    assert "validation_errors" in response.json()["detail"]
    assert response.json()["detail"]["validation_errors"][0]["type"] == "missing"
    assert response.json()["detail"]["validation_errors"][0]["loc"][0] == "masterdata"
    assert response.json()["detail"]["validation_errors"][0]["msg"] == "Field required"


async def test_check_global_config_status_general_exception(
    client_with_project_session: TestClient,
    global_config_default_path: Path,
) -> None:
    """Test 500 returns when general exception occurs in get_global_config_status."""
    with patch(
        "fmu_settings_api.services.project.find_global_config",
        side_effect=RuntimeError("Global config lookup failed"),
    ):
        response = client_with_project_session.get(f"{ROUTE}/global_config_status")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "An unexpected error occurred."}


async def test_check_global_config_status_with_disallowed_content(
    client_with_project_session: TestClient,
    global_config_default_path: Path,
) -> None:
    """Test 422 returned when global config has disallowed content.

    Tests the get_global_config_status endpoint.
    """
    with patch(
        "fmu_settings_api.services.project.find_global_config",
        side_effect=InvalidGlobalConfigurationError("Drogon data is not allowed"),
    ):
        response = client_with_project_session.get(f"{ROUTE}/global_config_status")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert (
            response.json()["detail"]["message"]
            == "The global config contains invalid or disallowed content."
        )
        assert response.json()["detail"]["error"] == "Drogon data is not allowed"


async def test_load_global_config_with_disallowed_content(
    client_with_project_session: TestClient,
    global_config_default_path: Path,
) -> None:
    """Test 422 returned when global config has disallowed content.

    Tests the post_global_config endpoint.
    """
    with patch(
        "fmu_settings_api.services.project.find_global_config",
        side_effect=InvalidGlobalConfigurationError("Drogon data is not allowed"),
    ):
        response = client_with_project_session.post(f"{ROUTE}/global_config")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert (
            response.json()["detail"]["message"]
            == "The global config contains invalid or disallowed content."
        )
        assert response.json()["detail"]["error"] == "Drogon data is not allowed"


# PATCH project/model #


async def test_patch_model_project(
    client_with_project_session: TestClient,
    model_data: dict[str, Any],
) -> None:
    """Test saving model data to project .fmu."""
    # Get project session and check that model is not set
    get_response = client_with_project_session.get(ROUTE)
    get_fmu_project = FMUProject.model_validate(get_response.json())
    assert get_fmu_project.config.model is None

    # Store model to project
    response = client_with_project_session.patch(f"{ROUTE}/model", json=model_data)
    assert response.status_code == status.HTTP_200_OK
    assert (
        response.json()["message"]
        == f"Saved model data to {get_fmu_project.path / '.fmu'}"
    )
    # Refetch the project to see that model is set
    get_response = client_with_project_session.get(ROUTE)
    get_fmu_project = FMUProject.model_validate(get_response.json())
    assert get_fmu_project.config.model is not None
    assert get_fmu_project.config.model == Model.model_validate(model_data)
    assert get_fmu_project.config.model.name == "Drogon"


async def test_patch_model_requires_project_session(
    client_with_session: TestClient,
    model_data: dict[str, Any],
) -> None:
    """Test saving model data to .fmu requires an active project."""
    response = client_with_session.patch(f"{ROUTE}/model", json=model_data)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
    assert response.json()["detail"] == "No FMU project directory open"


async def test_patch_model_no_directory_permissions(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
    model_data: dict[str, Any],
    no_permissions: Callable[[str | Path], AbstractContextManager[None]],
) -> None:
    """Test 403 returns when lacking permissions."""
    bad_project_dir = session_tmp_path / ".fmu"

    with no_permissions(bad_project_dir):
        response = client_with_project_session.patch(f"{ROUTE}/model", json=model_data)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {
        "detail": f"Permission denied accessing .fmu at {bad_project_dir}"
    }


async def test_patch_model_no_directory(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
    model_data: dict[str, Any],
) -> None:
    """Test that if .fmu/ is deleted during a session an error is raised."""
    project_dir = session_tmp_path / ".fmu"

    # remove project .fmu
    shutil.rmtree(project_dir)
    assert not project_dir.exists()

    response = client_with_project_session.patch(f"{ROUTE}/model", json=model_data)
    assert response.status_code == status.HTTP_404_NOT_FOUND, response.json()["detail"]


async def test_patch_model_general_exception(
    client_with_project_session: TestClient,
    model_data: dict[str, Any],
    session_manager: SessionManager,
) -> None:
    """Test 500 returns when general exceptions occur in patch_model."""
    # Get the project session to access its project_fmu_directory
    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    # Mock the project_fmu_directory.set_config_value to raise ValueError
    with patch.object(
        session.project_fmu_directory,
        "set_config_value",
        side_effect=ValueError("Invalid model data"),
    ):
        response = client_with_project_session.patch(f"{ROUTE}/model", json=model_data)
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "An unexpected error occurred."}


# PATCH project/access #


async def test_patch_access_project(
    client_with_project_session: TestClient,
    access_data: dict[str, Any],
) -> None:
    """Test saving access data to project .fmu."""
    # Get project session and check that access is not set
    get_response = client_with_project_session.get(ROUTE)
    get_fmu_project = FMUProject.model_validate(get_response.json())
    assert get_fmu_project.config.access is None

    # Store access to project
    response = client_with_project_session.patch(f"{ROUTE}/access", json=access_data)
    assert response.status_code == status.HTTP_200_OK
    assert (
        response.json()["message"]
        == f"Saved access data to {get_fmu_project.path / '.fmu'}"
    )
    # Refetch the project to see that access is set
    get_response = client_with_project_session.get(ROUTE)
    get_fmu_project = FMUProject.model_validate(get_response.json())
    assert get_fmu_project.config.access is not None
    assert get_fmu_project.config.access == Access.model_validate(access_data)
    assert get_fmu_project.config.access.asset.name == "Drogon"


async def test_patch_access_requires_project_session(
    client_with_session: TestClient,
    access_data: dict[str, Any],
) -> None:
    """Test saving access data to .fmu requires an active project."""
    response = client_with_session.patch(f"{ROUTE}/access", json=access_data)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
    assert response.json()["detail"] == "No FMU project directory open"


async def test_patch_access_no_directory_permissions(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
    access_data: dict[str, Any],
    no_permissions: Callable[[str | Path], AbstractContextManager[None]],
) -> None:
    """Test 403 returns when lacking permissions."""
    bad_project_dir = session_tmp_path / ".fmu"

    with no_permissions(bad_project_dir):
        response = client_with_project_session.patch(
            f"{ROUTE}/access", json=access_data
        )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {
        "detail": f"Permission denied accessing .fmu at {bad_project_dir}"
    }


async def test_patch_access_no_directory(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
    access_data: dict[str, Any],
) -> None:
    """Test that if .fmu/ is deleted during a session an error is raised."""
    project_dir = session_tmp_path / ".fmu"

    # remove project .fmu
    shutil.rmtree(project_dir)
    assert not project_dir.exists()

    response = client_with_project_session.patch(f"{ROUTE}/access", json=access_data)
    assert response.status_code == status.HTTP_404_NOT_FOUND, response.json()["detail"]


async def test_patch_access_general_exception(
    client_with_project_session: TestClient,
    access_data: dict[str, Any],
    session_manager: SessionManager,
) -> None:
    """Test 500 returns when general exceptions occur in patch_access."""
    # Get the project session to access its project_fmu_directory
    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    # Mock the project_fmu_directory.set_config_value to raise ValueError
    with patch.object(
        session.project_fmu_directory,
        "set_config_value",
        side_effect=ValueError("Invalid access data"),
    ):
        response = client_with_project_session.patch(
            f"{ROUTE}/access", json=access_data
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "An unexpected error occurred."}


async def test_create_opened_project_response_direct_exception() -> None:
    """Test the _create_opened_project_response function directly with invalid input."""
    # Create a mock that will cause an exception in the function
    mock_fmu_dir = Mock()
    mock_fmu_dir.config.load.side_effect = Exception("Test exception")

    mock_lock = Mock()
    mock_lock.is_acquired.return_value = True
    mock_fmu_dir._lock = mock_lock

    try:
        _create_opened_project_response(mock_fmu_dir)
        raise AssertionError("Expected Exception")
    except Exception as e:
        assert str(e) == "Test exception"


async def test_create_opened_project_response_permission_error() -> None:
    """Test the _create_opened_project_response function with PermissionError."""
    mock_fmu_dir = Mock()
    mock_fmu_dir.config.load.side_effect = PermissionError("Permission denied")

    mock_lock = Mock()
    mock_lock.is_acquired.return_value = True
    mock_fmu_dir._lock = mock_lock

    try:
        _create_opened_project_response(mock_fmu_dir)
        raise AssertionError("Expected HTTPException")
    except HTTPException as e:
        assert e.status_code == status.HTTP_403_FORBIDDEN
        assert "Permission denied accessing .fmu" in str(e.detail)


async def test_get_lock_status(
    client_with_session: TestClient,
    session_tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test that lock status endpoint returns current lock information."""
    existing_fmu_dir = init_fmu_directory(session_tmp_path)

    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    with patch(
        "fmu_settings_api.services.session.find_nearest_fmu_directory",
        return_value=existing_fmu_dir,
    ):
        response = client_with_session.get(ROUTE)
        assert response.status_code == status.HTTP_200_OK

        lock_response = client_with_session.get(f"{ROUTE}/lock_status")
        assert lock_response.status_code == status.HTTP_200_OK

        lock_status = lock_response.json()

        assert "is_lock_acquired" in lock_status
        assert "lock_file_exists" in lock_status
        assert "lock_info" in lock_status
        assert "lock_status_error" in lock_status
        assert "lock_file_read_error" in lock_status
        assert "last_lock_acquire_error" in lock_status
        assert "last_lock_release_error" in lock_status
        assert "last_lock_refresh_error" in lock_status

        assert isinstance(lock_status["is_lock_acquired"], bool)
        assert isinstance(lock_status["lock_file_exists"], bool)
        assert lock_status["lock_status_error"] is None or isinstance(
            lock_status["lock_status_error"], str
        )
        assert lock_status["lock_file_read_error"] is None or isinstance(
            lock_status["lock_file_read_error"], str
        )
        assert lock_status["last_lock_acquire_error"] is None or isinstance(
            lock_status["last_lock_acquire_error"], str
        )
        assert lock_status["last_lock_release_error"] is None or isinstance(
            lock_status["last_lock_release_error"], str
        )
        assert lock_status["last_lock_refresh_error"] is None or isinstance(
            lock_status["last_lock_refresh_error"], str
        )

        if lock_status["is_lock_acquired"] and lock_status["lock_file_exists"]:
            assert lock_status["lock_info"] is not None
            if isinstance(lock_status["lock_info"], dict):
                expected_fields: dict[str, type | tuple[type, ...]] = {
                    "pid": int,
                    "hostname": str,
                    "user": str,
                    "acquired_at": (int, float),
                    "expires_at": (int, float),
                    "version": str,
                }
                for field, expected_type in expected_fields.items():
                    if field in lock_status["lock_info"]:
                        assert isinstance(
                            lock_status["lock_info"][field], expected_type
                        )


async def test_get_lock_status_deletes_stale_lock(
    client_with_session: TestClient,
    session_tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test that lock status endpoint deletes stale lock and clears internal state."""
    existing_fmu_dir = init_fmu_directory(session_tmp_path)

    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    with patch(
        "fmu_settings_api.services.session.find_nearest_fmu_directory",
        return_value=existing_fmu_dir,
    ):
        response = client_with_session.get(ROUTE)
        assert response.status_code == status.HTTP_200_OK

        lock_path = existing_fmu_dir._lock.path
        assert lock_path.exists() is True
        lock_info = existing_fmu_dir._lock.load(force=True, store_cache=False)
        assert lock_info is not None

        future_time = lock_info.expires_at + 1
        with patch("time.time", return_value=future_time):
            assert existing_fmu_dir._lock._is_stale(lock_info) is True

            assert existing_fmu_dir._lock._cache is not None
            assert existing_fmu_dir._lock._acquired_at is not None

            lock_response = client_with_session.get(f"{ROUTE}/lock_status")
            assert lock_response.status_code == status.HTTP_200_OK

            lock_status = lock_response.json()
            assert lock_status["lock_file_exists"] is False
            assert lock_status["is_lock_acquired"] is False
            assert lock_status["lock_info"] is None

            assert existing_fmu_dir._lock._cache is None
            assert existing_fmu_dir._lock._acquired_at is None

        assert lock_path.exists() is False


async def test_get_lock_status_stale_lock_deletion_fails(
    client_with_session: TestClient,
    session_tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test that lock status endpoint handles stale lock deletion errors gracefully."""
    existing_fmu_dir = init_fmu_directory(session_tmp_path)

    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    with patch(
        "fmu_settings_api.services.session.find_nearest_fmu_directory",
        return_value=existing_fmu_dir,
    ):
        response = client_with_session.get(ROUTE)
        assert response.status_code == status.HTTP_200_OK

        lock_path = existing_fmu_dir._lock.path
        assert lock_path.exists() is True
        lock_info = existing_fmu_dir._lock.load(force=True, store_cache=False)
        assert lock_info is not None

        future_time = lock_info.expires_at + 1
        with (
            patch("time.time", return_value=future_time),
            patch("pathlib.Path.unlink") as mock_unlink,
        ):
            mock_unlink.side_effect = OSError("Permission denied")

            lock_response = client_with_session.get(f"{ROUTE}/lock_status")
            assert lock_response.status_code == status.HTTP_200_OK

            lock_status = lock_response.json()
            assert lock_status["lock_file_exists"] is True
            assert lock_status["lock_info"] is None
            assert lock_status["lock_file_read_error"] is not None
            assert (
                "Failed to delete stale lock file"
                in lock_status["lock_file_read_error"]
            )
            assert "Permission denied" in lock_status["lock_file_read_error"]

        lock_path.unlink()


async def test_get_lock_status_with_lock_status_error(
    client_with_session: TestClient,
    session_tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test lock status endpoint when is_acquired() fails."""
    existing_fmu_dir = init_fmu_directory(session_tmp_path)

    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    with patch(
        "fmu_settings_api.services.session.find_nearest_fmu_directory",
        return_value=existing_fmu_dir,
    ):
        response = client_with_session.get(ROUTE)
        assert response.status_code == status.HTTP_200_OK

        with patch.object(
            existing_fmu_dir._lock,
            "is_acquired",
            side_effect=Exception("Lock status check failed"),
        ):
            lock_response = client_with_session.get(f"{ROUTE}/lock_status")
            assert lock_response.status_code == status.HTTP_200_OK

            lock_status = lock_response.json()
            assert lock_status["is_lock_acquired"] is False
            expected_error = "Failed to check lock status: Lock status check failed"
            assert lock_status["lock_status_error"] == expected_error
            assert lock_status["lock_file_read_error"] is None
            assert lock_status["last_lock_acquire_error"] is None
            assert lock_status["last_lock_release_error"] is None
            assert lock_status["last_lock_refresh_error"] is None


async def test_get_lock_status_with_lock_file_read_error(
    client_with_session: TestClient,
    session_tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test lock status endpoint when lock file path access fails."""
    existing_fmu_dir = init_fmu_directory(session_tmp_path)

    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    with patch(
        "fmu_settings_api.services.session.find_nearest_fmu_directory",
        return_value=existing_fmu_dir,
    ):
        response = client_with_session.get(ROUTE)
        assert response.status_code == status.HTTP_200_OK

        mock_lock = Mock()
        mock_lock.is_acquired.return_value = False
        error_msg = "Permission denied accessing lock path"

        def raise_error_on_exists() -> None:
            raise PermissionError(error_msg)

        type(mock_lock).exists = property(lambda self: raise_error_on_exists())

        with patch.object(existing_fmu_dir, "_lock", mock_lock):
            lock_response = client_with_session.get(f"{ROUTE}/lock_status")
            assert lock_response.status_code == status.HTTP_200_OK

            lock_status = lock_response.json()
            assert lock_status["is_lock_acquired"] is False
            assert lock_status["lock_file_exists"] is False
            read_error = lock_status["lock_file_read_error"]
            assert "Failed to access lock file path" in read_error
            assert error_msg in read_error


async def test_get_lock_status_with_corrupted_lock_file(
    client_with_session: TestClient,
    session_tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test lock status endpoint with corrupted lock file JSON."""
    existing_fmu_dir = init_fmu_directory(session_tmp_path)

    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    with patch(
        "fmu_settings_api.services.session.find_nearest_fmu_directory",
        return_value=existing_fmu_dir,
    ):
        response = client_with_session.get(ROUTE)
        assert response.status_code == status.HTTP_200_OK

        mock_lock = Mock()
        mock_lock.is_acquired.return_value = False
        mock_lock.exists = True
        mock_lock.load.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)

        with patch.object(existing_fmu_dir, "_lock", mock_lock):
            lock_response = client_with_session.get(f"{ROUTE}/lock_status")
            assert lock_response.status_code == status.HTTP_200_OK

            lock_status = lock_response.json()
            assert lock_status["lock_file_exists"] is True
            assert lock_status["lock_info"] is None
            read_error = lock_status["lock_file_read_error"]
            assert "Failed to parse lock file" in read_error


async def test_get_lock_status_includes_session_error_fields(
    client_with_session: TestClient,
    session_tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test lock status endpoint includes session lock error fields."""
    existing_fmu_dir = init_fmu_directory(session_tmp_path)

    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    with patch(
        "fmu_settings_api.services.session.find_nearest_fmu_directory",
        return_value=existing_fmu_dir,
    ):
        response = client_with_session.get(ROUTE)
        assert response.status_code == status.HTTP_200_OK

        lock_response = client_with_session.get(f"{ROUTE}/lock_status")
        assert lock_response.status_code == status.HTTP_200_OK

        lock_status = lock_response.json()
        assert "last_lock_acquire_error" in lock_status
        assert "last_lock_release_error" in lock_status
        assert "last_lock_refresh_error" in lock_status


async def test_get_lock_status_with_lock_file_permission_error(
    client_with_session: TestClient,
    session_tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test lock status when lock file exists but can't be read due to permissions."""
    existing_fmu_dir = init_fmu_directory(session_tmp_path)

    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    with patch(
        "fmu_settings_api.services.session.find_nearest_fmu_directory",
        return_value=existing_fmu_dir,
    ):
        response = client_with_session.get(ROUTE)
        assert response.status_code == status.HTTP_200_OK

        mock_lock = Mock()
        mock_lock.is_acquired.return_value = False
        mock_lock.exists = True
        mock_lock.load.side_effect = PermissionError("Permission denied")

        with patch.object(existing_fmu_dir, "_lock", mock_lock):
            lock_response = client_with_session.get(f"{ROUTE}/lock_status")
            assert lock_response.status_code == status.HTTP_200_OK

            lock_status = lock_response.json()
            assert lock_status["is_lock_acquired"] is False
            assert lock_status["lock_file_exists"] is True
            read_error = lock_status["lock_file_read_error"]
            assert "Failed to read lock file: Permission denied" in read_error


async def test_get_lock_status_with_lock_file_processing_error(
    client_with_session: TestClient,
    session_tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test lock status when lock file processing fails with generic exception."""
    existing_fmu_dir = init_fmu_directory(session_tmp_path)

    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    with patch(
        "fmu_settings_api.services.session.find_nearest_fmu_directory",
        return_value=existing_fmu_dir,
    ):
        response = client_with_session.get(ROUTE)
        assert response.status_code == status.HTTP_200_OK

        mock_lock = Mock()
        mock_lock.is_acquired.return_value = False
        mock_lock.exists = True
        mock_lock.load.side_effect = RuntimeError("Unexpected lock file error")

        with patch.object(existing_fmu_dir, "_lock", mock_lock):
            lock_response = client_with_session.get(f"{ROUTE}/lock_status")
            assert lock_response.status_code == status.HTTP_200_OK

            lock_status = lock_response.json()
            assert lock_status["is_lock_acquired"] is False
            assert lock_status["lock_file_exists"] is True
            read_error = lock_status["lock_file_read_error"]
            assert "Failed to process lock file" in read_error
            assert "Unexpected lock file error" in read_error


async def test_get_lock_status_with_lock_file_not_exists(
    client_with_session: TestClient,
    session_tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test lock status when lock file path exists but file doesn't exist."""
    existing_fmu_dir = init_fmu_directory(session_tmp_path)

    ert_model_path = session_tmp_path / "project/24.0.3/ert/model"
    ert_model_path.mkdir(parents=True)
    monkeypatch.chdir(ert_model_path)

    with patch(
        "fmu_settings_api.services.session.find_nearest_fmu_directory",
        return_value=existing_fmu_dir,
    ):
        response = client_with_session.get(ROUTE)
        assert response.status_code == status.HTTP_200_OK

        mock_lock = Mock()
        mock_lock.is_acquired.return_value = False
        mock_lock.exists = False

        with patch.object(existing_fmu_dir, "_lock", mock_lock):
            lock_response = client_with_session.get(f"{ROUTE}/lock_status")
            assert lock_response.status_code == status.HTTP_200_OK

            lock_status = lock_response.json()
            assert lock_status["is_lock_acquired"] is False
            assert lock_status["lock_file_exists"] is False
            assert lock_status["lock_info"] is None
            assert lock_status["lock_file_read_error"] is None


async def test_get_lock_status_does_not_update_expiration(
    client_with_project_session: TestClient,
    session_id: str,
) -> None:
    """Test that lock status endpoint does not update the session expiration."""
    from fmu_settings_api.session import session_manager  # noqa: PLC0415

    before_acquire = await session_manager.get_session(
        session_id, extend_expiration=False
    )
    # Must be copied. Session is reference
    before_acquire_expiration = before_acquire.expires_at
    before_acquire_accessed = before_acquire.last_accessed

    # Acquire lock (or something.)
    client_with_project_session.post(f"{ROUTE}/lock_acquire")

    before_status = await session_manager.get_session(
        session_id, extend_expiration=False
    )
    before_expiration = before_status.expires_at
    before_accessed = before_status.last_accessed

    assert before_acquire_accessed < before_accessed
    assert before_acquire_expiration < before_expiration  # Updates expiration

    # Request
    client_with_project_session.get(f"{ROUTE}/lock_status")

    after_status = await session_manager.get_session(
        session_id, extend_expiration=False
    )

    assert before_accessed < after_status.last_accessed
    assert before_expiration == after_status.expires_at


# POST project/lock_acquire #


async def test_post_lock_acquire_success(
    client_with_project_session: TestClient,
    session_id: str,
) -> None:
    """Test lock acquire route returns writable project when lock is held."""
    from fmu_settings_api.session import session_manager  # noqa: PLC0415

    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    mock_lock = Mock()
    mock_lock.is_acquired.return_value = True
    mock_lock.refresh = Mock()
    session.project_fmu_directory._lock = mock_lock

    mock_try_acquire = AsyncMock(return_value=session)

    with patch(
        "fmu_settings_api.services.session.try_acquire_project_lock",
        mock_try_acquire,
    ):
        response = client_with_project_session.post(f"{ROUTE}/lock_acquire")

    mock_try_acquire.assert_awaited_once_with(session_id)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"message": "Project lock acquired."}


async def test_post_lock_acquire_conflict_returns_read_only(
    client_with_project_session: TestClient,
    session_id: str,
) -> None:
    """Test lock acquire route returns read-only when acquisition fails."""
    from fmu_settings_api.session import session_manager  # noqa: PLC0415

    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    mock_lock = Mock()
    mock_lock.is_acquired.return_value = False
    mock_lock.refresh = Mock()
    session.project_fmu_directory._lock = mock_lock
    session.lock_errors.acquire = "Lock held elsewhere"

    mock_try_acquire = AsyncMock(return_value=session)

    with patch(
        "fmu_settings_api.services.session.try_acquire_project_lock",
        mock_try_acquire,
    ):
        response = client_with_project_session.post(f"{ROUTE}/lock_acquire")

    mock_try_acquire.assert_awaited_once_with(session_id)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "message": (
            "Project remains read-only because the lock could not be acquired. "
            "Check lock status for details."
        )
    }


async def test_post_lock_acquire_session_not_found(
    client_with_project_session: TestClient,
) -> None:
    """Test lock acquire route returns 401 when session is missing."""
    mock_try_acquire = AsyncMock(side_effect=SessionNotFoundError("Session not found"))

    with patch(
        "fmu_settings_api.services.session.try_acquire_project_lock",
        mock_try_acquire,
    ):
        response = client_with_project_session.post(f"{ROUTE}/lock_acquire")

    mock_try_acquire.assert_awaited_once()
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "Session not found"}


async def test_post_lock_acquire_unexpected_error(
    client_with_project_session: TestClient,
) -> None:
    """Test lock acquire route returns 500 on unexpected error."""
    mock_try_acquire = AsyncMock(side_effect=RuntimeError("boom"))

    with patch(
        "fmu_settings_api.services.session.try_acquire_project_lock",
        mock_try_acquire,
    ):
        response = client_with_project_session.post(f"{ROUTE}/lock_acquire")

    mock_try_acquire.assert_awaited_once()
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json() == {"detail": "An unexpected error occurred."}


# POST project/lock_refresh #


async def test_post_lock_refresh_success(
    client_with_project_session: TestClient,
    session_id: str,
) -> None:
    """Test lock refresh route returns success message after refreshing the lock."""
    from fmu_settings_api.session import session_manager  # noqa: PLC0415

    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    mock_lock = Mock()
    mock_lock.is_acquired.return_value = True
    mock_lock.exists = True
    mock_lock.refresh = Mock()
    mock_lock.load.return_value = {
        "user": "test_user",
        "hostname": "test_host",
        "pid": 12345,
        "acquired_at": 1234567890.0,
        "expires_at": 1234569090.0,
        "version": "1.0.0",
    }
    session.project_fmu_directory._lock = mock_lock

    response = client_with_project_session.post(f"{ROUTE}/lock_refresh")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["message"] == "Project lock refreshed successfully."
    mock_lock.refresh.assert_called_once()


async def test_post_lock_refresh_when_not_held(
    client_with_project_session: TestClient,
    session_id: str,
) -> None:
    """Test lock refresh route when lock is not held."""
    from fmu_settings_api.session import session_manager  # noqa: PLC0415

    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    mock_lock = Mock()
    mock_lock.is_acquired.return_value = False
    mock_lock.exists = False
    mock_lock.refresh = Mock()
    session.project_fmu_directory._lock = mock_lock

    response = client_with_project_session.post(f"{ROUTE}/lock_refresh")

    assert response.status_code == status.HTTP_200_OK
    assert "message" in response.json()
    assert "not currently held" in response.json()["message"]
    mock_lock.refresh.assert_not_called()


async def test_post_lock_refresh_session_not_found(
    client_with_session: TestClient,
) -> None:
    """Test lock refresh route returns 401 when no project session exists."""
    response = client_with_session.post(f"{ROUTE}/lock_refresh")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "No FMU project directory open"


async def test_post_lock_refresh_records_refresh_error(
    client_with_project_session: TestClient,
    session_id: str,
) -> None:
    """Test lock refresh route records error if refresh fails."""
    from fmu.settings._resources.lock_manager import LockError  # noqa: PLC0415

    from fmu_settings_api.session import session_manager  # noqa: PLC0415

    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    mock_lock = Mock()
    mock_lock.is_acquired.return_value = True
    mock_lock.exists = True
    mock_lock.refresh.side_effect = LockError("Lock conflict")
    mock_lock.load.return_value = {
        "user": "test_user",
        "hostname": "test_host",
        "pid": 12345,
        "acquired_at": 1234567890.0,
        "expires_at": 1234569090.0,
        "version": "1.0.0",
    }
    session.project_fmu_directory._lock = mock_lock

    response = client_with_project_session.post(f"{ROUTE}/lock_refresh")

    assert response.status_code == status.HTTP_200_OK
    assert "message" in response.json()
    assert "error occurred" in response.json()["message"]
    assert "Lock conflict" in response.json()["message"]


async def test_post_lock_refresh_permission_error(
    client_with_project_session: TestClient,
    session_id: str,
) -> None:
    """Test lock refresh route swallows permission errors gracefully."""
    from fmu_settings_api.session import session_manager  # noqa: PLC0415

    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    mock_lock = Mock()
    mock_lock.is_acquired.return_value = True
    mock_lock.exists = True
    mock_lock.refresh.side_effect = PermissionError("Permission denied")
    mock_lock.load.return_value = {
        "user": "test_user",
        "hostname": "test_host",
        "pid": 12345,
        "acquired_at": 1234567890.0,
        "expires_at": 1234569090.0,
        "version": "1.0.0",
    }
    session.project_fmu_directory._lock = mock_lock

    response = client_with_project_session.post(f"{ROUTE}/lock_refresh")

    assert response.status_code == status.HTTP_200_OK
    assert "message" in response.json()
    assert "error occurred" in response.json()["message"]
    assert "Permission denied" in response.json()["message"]


async def test_post_lock_refresh_general_exception(
    client_with_project_session: TestClient,
) -> None:
    """Test lock refresh route returns 500 on unexpected error in get_lock_status."""
    with patch(
        "fmu_settings_api.services.session.SessionService.get_lock_status",
        side_effect=RuntimeError("Unexpected error"),
    ):
        response = client_with_project_session.post(f"{ROUTE}/lock_refresh")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["detail"] == "An unexpected error occurred."


# GET project/rms_projects #


async def test_get_rms_projects_requires_project_session(
    client_with_session: TestClient,
) -> None:
    """Test getting RMS projects requires an active project session."""
    response = client_with_session.get(f"{ROUTE}/rms_projects")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
    assert response.json()["detail"] == "No FMU project directory open"


async def test_get_rms_projects_empty_list(
    client_with_project_session: TestClient,
) -> None:
    """Test getting RMS projects returns empty list when none exist."""
    response = client_with_project_session.get(f"{ROUTE}/rms_projects")
    assert response.status_code == status.HTTP_200_OK, response.json()

    result = response.json()
    assert "results" in result
    assert isinstance(result["results"], list)
    assert len(result["results"]) == 0


async def test_get_rms_projects_returns_list(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
    session_manager: SessionManager,
) -> None:
    """Test getting RMS projects returns list of found projects."""
    rms_dir = session_tmp_path / "rms" / "model"
    rms_dir.mkdir(parents=True)

    project1 = rms_dir / "project1.rms13.1.2"
    project2 = rms_dir / "project2.rms14.2.2"
    project1.mkdir()
    project2.mkdir()

    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    with patch.object(
        session.project_fmu_directory,
        "find_rms_projects",
        return_value=[project1, project2],
    ):
        response = client_with_project_session.get(f"{ROUTE}/rms_projects")
        assert response.status_code == status.HTTP_200_OK, response.json()

        result = response.json()
        assert "results" in result
        assert isinstance(result["results"], list)
        assert len(result["results"]) == 2  # noqa: PLR2004

        for item in result["results"]:
            assert "path" in item
            assert isinstance(item["path"], str)
            assert Path(item["path"]).exists()


async def test_get_rms_projects_permission_error(
    client_with_project_session: TestClient,
    session_manager: SessionManager,
) -> None:
    """Test 403 when scanning RMS projects hits permission errors."""
    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    with patch.object(
        session.project_fmu_directory,
        "find_rms_projects",
        side_effect=PermissionError("No permission"),
    ):
        response = client_with_project_session.get(f"{ROUTE}/rms_projects")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {
        "detail": "Permission denied while scanning for RMS projects."
    }


async def test_get_rms_projects_file_not_found(
    client_with_project_session: TestClient,
    session_manager: SessionManager,
) -> None:
    """Test 404 when RMS project scan raises FileNotFoundError."""
    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    with patch.object(
        session.project_fmu_directory,
        "find_rms_projects",
        side_effect=FileNotFoundError("Project directory missing"),
    ):
        response = client_with_project_session.get(f"{ROUTE}/rms_projects")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "Project directory missing"}


async def test_get_rms_projects_general_exception(
    client_with_project_session: TestClient,
    session_manager: SessionManager,
) -> None:
    """Test 500 returns when general exceptions occur in get_rms_projects."""
    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    with patch.object(
        session.project_fmu_directory,
        "find_rms_projects",
        side_effect=RuntimeError("Failed to scan directories"),
    ):
        response = client_with_project_session.get(f"{ROUTE}/rms_projects")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "An unexpected error occurred."}


# PATCH project/rms #


async def test_patch_rms_requires_project_session(
    client_with_session: TestClient,
    session_tmp_path: Path,
) -> None:
    """Test saving RMS project path requires an active project session."""
    rms_path = session_tmp_path / "rms/model/project.rms14.2.2"
    response = client_with_session.patch(
        f"{ROUTE}/rms",
        json={"path": str(rms_path)},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.json()
    assert response.json()["detail"] == "No FMU project directory open"


async def test_patch_rms_success(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
) -> None:
    """Test saving RMS project path to project .fmu config."""
    rms_path = session_tmp_path / "rms/model/project.rms14.2.2"
    rms_path.mkdir(parents=True)

    get_response = client_with_project_session.get(ROUTE)
    get_fmu_project = FMUProject.model_validate(get_response.json())
    assert get_fmu_project.config.rms is None

    mock_rms_config = Mock()
    mock_rms_config.version = "14.2.2"

    with patch(
        "fmu_settings_api.services.rms.RmsConfig",
        return_value=mock_rms_config,
    ):
        response = client_with_project_session.patch(
            f"{ROUTE}/rms",
            json={"path": str(rms_path)},
        )
    assert response.status_code == status.HTTP_200_OK
    expected_message = (
        f"Saved RMS project path with RMS version 14.2.2 "
        f"to {get_fmu_project.path / '.fmu'}"
    )
    assert response.json()["message"] == expected_message

    get_response = client_with_project_session.get(ROUTE)
    get_fmu_project = FMUProject.model_validate(get_response.json())
    assert get_fmu_project.config.rms is not None
    assert Path(get_fmu_project.config.rms.path) == rms_path


async def test_patch_rms_updates_existing(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
) -> None:
    """Test updating an existing RMS project path."""
    rms_path1 = session_tmp_path / "rms/model/project1.rms14.2.2"
    rms_path1.mkdir(parents=True)

    rms_path2 = session_tmp_path / "rms/model/project2.rms14.2.2"
    rms_path2.mkdir(parents=True)

    mock_rms_config = Mock()
    mock_rms_config.version = "14.2.2"

    with patch(
        "fmu_settings_api.services.rms.RmsConfig",
        return_value=mock_rms_config,
    ):
        response = client_with_project_session.patch(
            f"{ROUTE}/rms",
            json={"path": str(rms_path1)},
        )
        assert response.status_code == status.HTTP_200_OK

        get_response = client_with_project_session.get(ROUTE)
        get_fmu_project = FMUProject.model_validate(get_response.json())
        assert get_fmu_project.config.rms is not None
        assert Path(get_fmu_project.config.rms.path) == rms_path1

        response = client_with_project_session.patch(
            f"{ROUTE}/rms",
            json={"path": str(rms_path2)},
        )
        assert response.status_code == status.HTTP_200_OK

        get_response = client_with_project_session.get(ROUTE)
        get_fmu_project = FMUProject.model_validate(get_response.json())
        assert get_fmu_project.config.rms is not None
        assert Path(get_fmu_project.config.rms.path) == rms_path2


async def test_patch_rms_no_directory_permissions(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
    no_permissions: Callable[[str | Path], AbstractContextManager[None]],
) -> None:
    """Test 403 returns when lacking permissions to write to .fmu."""
    bad_project_dir = session_tmp_path / ".fmu"
    rms_path = session_tmp_path / "rms/model/project.rms14.2.2"

    with no_permissions(bad_project_dir):
        response = client_with_project_session.patch(
            f"{ROUTE}/rms",
            json={"path": str(rms_path)},
        )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {
        "detail": f"Permission denied accessing .fmu at {bad_project_dir}"
    }


async def test_patch_rms_no_directory(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
) -> None:
    """Test that if .fmu/ is deleted during a session an error is raised."""
    project_dir = session_tmp_path / ".fmu"
    rms_path = session_tmp_path / "rms/model/project.rms14.2.2"

    shutil.rmtree(project_dir)
    assert not project_dir.exists()

    response = client_with_project_session.patch(
        f"{ROUTE}/rms",
        json={"path": str(rms_path)},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND, response.json()["detail"]


async def test_patch_rms_path_not_found(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
) -> None:
    """Test 404 returns when RMS path does not exist."""
    rms_path = session_tmp_path / "missing_project.rms14.2.2"

    with patch(
        "fmu_settings_api.services.project.RmsService.get_rms_version",
        side_effect=FileNotFoundError("master file not found"),
    ):
        response = client_with_project_session.patch(
            f"{ROUTE}/rms",
            json={"path": str(rms_path)},
        )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": f"RMS project path {rms_path} does not exist."}


async def test_patch_rms_general_exception(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
    session_manager: SessionManager,
) -> None:
    """Test 500 returns when general exceptions occur in patch_rms."""
    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    rms_path = session_tmp_path / "rms/model/project.rms14.2.2"
    rms_path.mkdir(parents=True)

    mock_rms_config = Mock()
    mock_rms_config.version = "14.2.2"

    with (
        patch(
            "fmu_settings_api.services.rms.RmsConfig",
            return_value=mock_rms_config,
        ),
        patch.object(
            session.project_fmu_directory,
            "update_config",
            side_effect=ValueError("Invalid RMS project path"),
        ),
    ):
        response = client_with_project_session.patch(
            f"{ROUTE}/rms",
            json={"path": str(rms_path)},
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "An unexpected error occurred."}


# PATCH project/rms/coordinate_system #


async def test_patch_rms_coordinate_system_requires_project_session(
    client_with_session: TestClient,
) -> None:
    """Test saving RMS coordinate system requires an active project session."""
    response = client_with_session.patch(
        f"{ROUTE}/rms/coordinate_system",
        json={"name": "westeros"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "No FMU project directory open"


async def test_patch_rms_coordinate_system_requires_rms_config(
    client_with_project_session: TestClient,
) -> None:
    """Test 422 returns when RMS config is not set."""
    response = client_with_project_session.patch(
        f"{ROUTE}/rms/coordinate_system",
        json={"name": "westeros"},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "RMS project path must be set" in response.json()["detail"]


async def test_patch_rms_coordinate_system_success(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
) -> None:
    """Test saving RMS coordinate system to project .fmu config."""
    rms_path = session_tmp_path / "rms/model/project.rms14.2.2"
    rms_path.mkdir(parents=True)

    mock_rms_config = Mock()
    mock_rms_config.version = "14.2.2"

    with patch(
        "fmu_settings_api.services.rms.RmsConfig",
        return_value=mock_rms_config,
    ):
        client_with_project_session.patch(
            f"{ROUTE}/rms",
            json={"path": str(rms_path)},
        )

    response = client_with_project_session.patch(
        f"{ROUTE}/rms/coordinate_system",
        json={"name": "westeros"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert "coordinate system" in response.json()["message"]

    get_response = client_with_project_session.get(ROUTE)
    get_fmu_project = FMUProject.model_validate(get_response.json())
    assert get_fmu_project.config.rms is not None
    assert get_fmu_project.config.rms.coordinate_system is not None
    assert get_fmu_project.config.rms.coordinate_system.name == "westeros"


# PATCH project/rms/zones #


async def test_patch_rms_zones_requires_project_session(
    client_with_session: TestClient,
) -> None:
    """Test saving RMS zones requires an active project session."""
    response = client_with_session.patch(
        f"{ROUTE}/rms/zones",
        json=[
            {"name": "Zone A", "top_horizon_name": "Top", "base_horizon_name": "Base"}
        ],
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "No FMU project directory open"


async def test_patch_rms_zones_requires_rms_config(
    client_with_project_session: TestClient,
) -> None:
    """Test 422 returns when RMS config is not set."""
    response = client_with_project_session.patch(
        f"{ROUTE}/rms/zones",
        json=[
            {"name": "Zone A", "top_horizon_name": "Top", "base_horizon_name": "Base"}
        ],
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "RMS project path must be set" in response.json()["detail"]


async def test_patch_rms_zones_success(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
) -> None:
    """Test saving RMS zones to project .fmu config."""
    rms_path = session_tmp_path / "rms/model/project.rms14.2.2"
    rms_path.mkdir(parents=True)

    mock_rms_config = Mock()
    mock_rms_config.version = "14.2.2"

    with patch(
        "fmu_settings_api.services.rms.RmsConfig",
        return_value=mock_rms_config,
    ):
        client_with_project_session.patch(
            f"{ROUTE}/rms",
            json={"path": str(rms_path)},
        )

    zones_data = [
        {"name": "Zone A", "top_horizon_name": "Top A", "base_horizon_name": "Base A"},
        {"name": "Zone B", "top_horizon_name": "Top B", "base_horizon_name": "Base B"},
    ]
    response = client_with_project_session.patch(
        f"{ROUTE}/rms/zones",
        json=zones_data,
    )
    assert response.status_code == status.HTTP_200_OK
    assert "zones" in response.json()["message"]

    get_response = client_with_project_session.get(ROUTE)
    get_fmu_project = FMUProject.model_validate(get_response.json())
    assert get_fmu_project.config.rms is not None
    assert get_fmu_project.config.rms.zones is not None
    assert len(get_fmu_project.config.rms.zones) == 2  # noqa: PLR2004
    assert get_fmu_project.config.rms.zones[0].name == "Zone A"
    assert get_fmu_project.config.rms.zones[1].name == "Zone B"


# PATCH project/rms/horizons #


async def test_patch_rms_horizons_requires_project_session(
    client_with_session: TestClient,
) -> None:
    """Test saving RMS horizons requires an active project session."""
    response = client_with_session.patch(
        f"{ROUTE}/rms/horizons",
        json=[{"name": "Horizon 1"}],
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "No FMU project directory open"


async def test_patch_rms_horizons_requires_rms_config(
    client_with_project_session: TestClient,
) -> None:
    """Test 422 returns when RMS config is not set."""
    response = client_with_project_session.patch(
        f"{ROUTE}/rms/horizons",
        json=[{"name": "Horizon 1", "type": "calculated"}],
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    detail = response.json()["detail"]
    assert "RMS project path must be set" in str(detail)


async def test_patch_rms_horizons_success(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
) -> None:
    """Test saving RMS horizons to project .fmu config."""
    rms_path = session_tmp_path / "rms/model/project.rms14.2.2"
    rms_path.mkdir(parents=True)

    mock_rms_config = Mock()
    mock_rms_config.version = "14.2.2"

    with patch(
        "fmu_settings_api.services.rms.RmsConfig",
        return_value=mock_rms_config,
    ):
        client_with_project_session.patch(
            f"{ROUTE}/rms",
            json={"path": str(rms_path)},
        )

    horizons_data = [
        {"name": "H1", "type": "calculated"},
        {"name": "H2", "type": "interpreted"},
        {"name": "H3", "type": "calculated"},
    ]
    response = client_with_project_session.patch(
        f"{ROUTE}/rms/horizons",
        json=horizons_data,
    )
    assert response.status_code == status.HTTP_200_OK
    assert "horizons" in response.json()["message"]

    get_response = client_with_project_session.get(ROUTE)
    get_fmu_project = FMUProject.model_validate(get_response.json())
    assert get_fmu_project.config.rms is not None
    assert get_fmu_project.config.rms.horizons is not None
    assert len(get_fmu_project.config.rms.horizons) == 3  # noqa: PLR2004
    assert [h.name for h in get_fmu_project.config.rms.horizons] == ["H1", "H2", "H3"]


# PATCH project/rms/wells #


async def test_patch_rms_wells_requires_project_session(
    client_with_session: TestClient,
) -> None:
    """Test saving RMS wells requires an active project session."""
    response = client_with_session.patch(
        f"{ROUTE}/rms/wells",
        json=[{"name": "Well 1"}],
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "No FMU project directory open"


async def test_patch_rms_wells_requires_rms_config(
    client_with_project_session: TestClient,
) -> None:
    """Test 422 returns when RMS config is not set."""
    response = client_with_project_session.patch(
        f"{ROUTE}/rms/wells",
        json=[{"name": "Well 1"}],
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "RMS project path must be set" in response.json()["detail"]


async def test_patch_rms_wells_success(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
) -> None:
    """Test saving RMS wells to project .fmu config."""
    rms_path = session_tmp_path / "rms/model/project.rms14.2.2"
    rms_path.mkdir(parents=True)

    mock_rms_config = Mock()
    mock_rms_config.version = "14.2.2"

    with patch(
        "fmu_settings_api.services.rms.RmsConfig",
        return_value=mock_rms_config,
    ):
        client_with_project_session.patch(
            f"{ROUTE}/rms",
            json={"path": str(rms_path)},
        )

    wells_data = [{"name": "W1"}, {"name": "W2"}]
    response = client_with_project_session.patch(
        f"{ROUTE}/rms/wells",
        json=wells_data,
    )
    assert response.status_code == status.HTTP_200_OK
    assert "wells" in response.json()["message"]

    get_response = client_with_project_session.get(ROUTE)
    get_fmu_project = FMUProject.model_validate(get_response.json())
    assert get_fmu_project.config.rms is not None
    assert get_fmu_project.config.rms.wells is not None
    assert len(get_fmu_project.config.rms.wells) == 2  # noqa: PLR2004
    assert [w.name for w in get_fmu_project.config.rms.wells] == ["W1", "W2"]


# GET project/cache #


async def test_get_cache_returns_resource_revisions(
    client_with_project_session: TestClient,
    session_manager: SessionManager,
) -> None:
    """Test cache list returns stored revision names."""
    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    fmu_dir = session.project_fmu_directory
    payload = {"example": True}
    revision_path = fmu_dir.cache.store_revision(
        Path("config.json"), json.dumps(payload)
    )
    assert revision_path is not None

    response = client_with_project_session.get(
        f"{ROUTE}/cache", params={"resource": "config.json"}
    )
    assert response.status_code == status.HTTP_200_OK
    assert revision_path.name in response.json()["revisions"]


async def test_get_cache_resource_permission_error(
    client_with_project_session: TestClient,
    session_manager: SessionManager,
    no_permissions: Callable[[str | Path], AbstractContextManager[None]],
) -> None:
    """Test 403 returns when cache directory lacks permissions."""
    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    fmu_dir = session.project_fmu_directory
    revision_path = fmu_dir.cache.store_revision(
        Path("config.json"), json.dumps({"example": True})
    )
    assert revision_path is not None

    with no_permissions(revision_path.parent):
        response = client_with_project_session.get(
            f"{ROUTE}/cache", params={"resource": "config.json"}
        )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {
        "detail": f"Permission denied accessing .fmu at {fmu_dir.path}"
    }


# GET project/cache/{revision_id} #


async def test_get_cache_revision_returns_resource_content(
    client_with_project_session: TestClient,
    session_manager: SessionManager,
) -> None:
    """Test fetching a cache revision returns parsed JSON."""
    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    fmu_dir = session.project_fmu_directory
    payload = fmu_dir.config.load().model_dump(mode="json")
    revision_path = fmu_dir.cache.store_revision(
        Path("config.json"), json.dumps(payload)
    )
    assert revision_path is not None

    response = client_with_project_session.get(
        f"{ROUTE}/cache/{revision_path.name}", params={"resource": "config.json"}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"] == payload


async def test_get_cache_revision_returns_mappings_content(
    client_with_project_session: TestClient,
    session_manager: SessionManager,
) -> None:
    """Test fetching a mappings cache revision returns parsed JSON."""
    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    fmu_dir = session.project_fmu_directory
    payload = Mappings().model_dump(mode="json")
    payload["wells"] = ["W1"]
    revision_path = fmu_dir.cache.store_revision(
        Path("mappings.json"), json.dumps(payload)
    )
    assert revision_path is not None

    response = client_with_project_session.get(
        f"{ROUTE}/cache/{revision_path.name}", params={"resource": "mappings.json"}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"] == payload


async def test_get_cache_revision_resource_not_found(
    client_with_project_session: TestClient,
) -> None:
    """Test 404 returns for missing cache revision."""
    response = client_with_project_session.get(
        f"{ROUTE}/cache/missing.json", params={"resource": "config.json"}
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {
        "detail": ("Cache revision 'missing.json' not found for resource 'config.json'")
    }


async def test_get_cache_revision_invalid_resource_json(
    client_with_project_session: TestClient,
    session_manager: SessionManager,
) -> None:
    """Test 422 returns for invalid JSON in cache revision."""
    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    fmu_dir = session.project_fmu_directory
    revision_path = fmu_dir.cache.store_revision(Path("config.json"), "not json")
    assert revision_path is not None

    response = client_with_project_session.get(
        f"{ROUTE}/cache/{revision_path.name}", params={"resource": "config.json"}
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "Invalid cached content for 'config.json'" in response.json()["detail"]


async def test_get_cache_revision_resource_permission_error(
    client_with_project_session: TestClient,
    session_manager: SessionManager,
) -> None:
    """Test 403 returns when cache revision is not readable."""
    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    fmu_dir = session.project_fmu_directory
    revision_path = fmu_dir.cache.store_revision(
        Path("config.json"), json.dumps({"example": True})
    )
    assert revision_path is not None

    original_mode = revision_path.stat().st_mode
    revision_path.chmod(0)  # remove all permissions
    try:
        response = client_with_project_session.get(
            f"{ROUTE}/cache/{revision_path.name}", params={"resource": "config.json"}
        )
    finally:
        revision_path.chmod(original_mode)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {
        "detail": f"Permission denied accessing .fmu at {fmu_dir.path}"
    }


# POST project/cache/restore/{revision_id} #


async def test_post_cache_restore_updates_resource(
    client_with_project_session: TestClient,
    session_manager: SessionManager,
) -> None:
    """Test restoring cache revision updates the resource."""
    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    fmu_dir = session.project_fmu_directory
    current_config = fmu_dir.config.load()
    updated_config = current_config.model_dump(mode="json")
    updated_config["cache_max_revisions"] = current_config.cache_max_revisions + 1

    revision_path = fmu_dir.cache.store_revision(
        Path("config.json"), json.dumps(updated_config)
    )
    assert revision_path is not None

    response = client_with_project_session.post(
        f"{ROUTE}/cache/restore/{revision_path.name}",
        params={"resource": "config.json"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "message": f"Restored config.json from revision {revision_path.name}"
    }
    assert (
        fmu_dir.config.load(force=True).cache_max_revisions
        == updated_config["cache_max_revisions"]
    )


async def test_post_cache_restore_updates_mappings(
    client_with_project_session: TestClient,
    session_manager: SessionManager,
) -> None:
    """Test restoring mappings cache revision updates the resource."""
    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    fmu_dir = session.project_fmu_directory
    payload = Mappings().model_dump(mode="json")
    payload["wells"] = ["W2"]

    revision_path = fmu_dir.cache.store_revision(
        Path("mappings.json"), json.dumps(payload)
    )
    assert revision_path is not None

    response = client_with_project_session.post(
        f"{ROUTE}/cache/restore/{revision_path.name}",
        params={"resource": "mappings.json"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "message": f"Restored mappings.json from revision {revision_path.name}"
    }
    restored = json.loads(fmu_dir.read_text_file(Path("mappings.json")))
    assert restored == payload


async def test_post_cache_restore_resource_missing_file(
    client_with_project_session: TestClient,
    session_manager: SessionManager,
) -> None:
    """Test restore succeeds when the current resource file is missing."""
    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    fmu_dir = session.project_fmu_directory
    current_config = fmu_dir.config.load()
    updated_config = current_config.model_dump(mode="json")
    updated_config["cache_max_revisions"] = current_config.cache_max_revisions + 2

    revision_path = fmu_dir.cache.store_revision(
        Path("config.json"), json.dumps(updated_config)
    )
    assert revision_path is not None

    fmu_dir.config.path.unlink()
    response = client_with_project_session.post(
        f"{ROUTE}/cache/restore/{revision_path.name}",
        params={"resource": "config.json"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert (
        fmu_dir.config.load(force=True).cache_max_revisions
        == updated_config["cache_max_revisions"]
    )


async def test_post_cache_restore_resource_not_found(
    client_with_project_session: TestClient,
) -> None:
    """Test 404 returns for missing cache revision on restore."""
    response = client_with_project_session.post(
        f"{ROUTE}/cache/restore/missing.json",
        params={"resource": "config.json"},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {
        "detail": ("Cache revision 'missing.json' not found for resource 'config.json'")
    }


async def test_post_cache_restore_invalid_resource_content(
    client_with_project_session: TestClient,
    session_manager: SessionManager,
) -> None:
    """Test 422 returns for invalid cached content."""
    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    fmu_dir = session.project_fmu_directory
    revision_path = fmu_dir.cache.store_revision(
        Path("config.json"), json.dumps({"cache_max_revisions": 1})
    )
    assert revision_path is not None

    response = client_with_project_session.post(
        f"{ROUTE}/cache/restore/{revision_path.name}",
        params={"resource": "config.json"},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "Invalid cached content" in response.json()["detail"]


async def test_post_cache_restore_resource_permission_error(
    client_with_project_session: TestClient,
    session_manager: SessionManager,
    no_permissions: Callable[[str | Path], AbstractContextManager[None]],
) -> None:
    """Test 403 returns when restore cannot write the resource."""
    session_id = client_with_project_session.cookies.get(
        settings.SESSION_COOKIE_KEY, None
    )
    assert session_id is not None
    session = await session_manager.get_session(session_id)
    assert isinstance(session, ProjectSession)

    fmu_dir = session.project_fmu_directory
    current_config = fmu_dir.config.load()
    updated_config = current_config.model_dump(mode="json")
    updated_config["cache_max_revisions"] = current_config.cache_max_revisions + 1

    revision_path = fmu_dir.cache.store_revision(
        Path("config.json"), json.dumps(updated_config)
    )
    assert revision_path is not None

    with no_permissions(fmu_dir.config.path):
        response = client_with_project_session.post(
            f"{ROUTE}/cache/restore/{revision_path.name}",
            params={"resource": "config.json"},
        )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {
        "detail": f"Permission denied accessing .fmu at {fmu_dir.path}"
    }
