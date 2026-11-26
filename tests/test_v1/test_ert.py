"""Tests the /api/v1/project/ert routes."""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from fmu_settings_api.models.ert import ErtConfigValidationResult, ErtRmsProjectList
from fmu_settings_api.services.ert import ErtService, ErtUnavailableError

ROUTE = "/api/v1/project/ert"

VALID = ErtConfigValidationResult(valid=True)
INVALID = ErtConfigValidationResult.model_validate(
    {"valid": False, "errors": [{"message": "bad", "line": 1, "column": 18}]}
)


@pytest.fixture(autouse=True)
def mock_warm_up() -> Generator[AsyncMock]:
    """Avoid starting ERT when listing configs."""
    with patch(
        "fmu_settings_api.v1.routes.ert.warm_up_ert_validator", new_callable=AsyncMock
    ) as warm_up:
        yield warm_up


def _model_dir(session_tmp_path: Path) -> Path:
    model_dir = session_tmp_path / "ert" / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    return model_dir


async def test_list_and_get_configs(
    client_with_project_session: TestClient,
    session_tmp_path: Path,
    mock_warm_up: AsyncMock,
) -> None:
    """Lists and reads .ert files in ert/model, warming up the validator."""
    (_model_dir(session_tmp_path) / "a.ert").write_text("NUM_REALIZATIONS 1\n")

    response = client_with_project_session.get(f"{ROUTE}/configs")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"files": ["a.ert"]}
    mock_warm_up.assert_awaited_once()

    response = client_with_project_session.get(f"{ROUTE}/configs/a.ert")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"content": "NUM_REALIZATIONS 1\n"}

    response = client_with_project_session.get(f"{ROUTE}/configs/missing.ert")
    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_routes_require_project_session(client_with_session: TestClient) -> None:
    """ERT routes require an open project."""
    response = client_with_session.get(f"{ROUTE}/configs")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_invalid_file_name_rejected(
    client_with_project_session: TestClient,
) -> None:
    """File names must be plain .ert names."""
    response = client_with_project_session.put(
        f"{ROUTE}/configs/bad name.txt", json={"content": ""}
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    response = client_with_project_session.post(
        f"{ROUTE}/validate", json={"name": "../x.ert", "content": ""}
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_validate(client_with_project_session: TestClient) -> None:
    """Returns the validation result."""
    with patch.object(
        ErtService, "validate", AsyncMock(return_value=INVALID)
    ) as validate:
        response = client_with_project_session.post(
            f"{ROUTE}/validate", json={"name": "a.ert", "content": "X"}
        )
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == INVALID.model_dump()
    validate.assert_awaited_once_with("a.ert", "X")


async def test_validate_ert_unavailable(
    client_with_project_session: TestClient,
) -> None:
    """Returns 503 when ERT is not available."""
    with patch.object(
        ErtService, "validate", AsyncMock(side_effect=ErtUnavailableError("no ert"))
    ):
        response = client_with_project_session.post(
            f"{ROUTE}/validate", json={"name": "a.ert", "content": "X"}
        )
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {"detail": "no ert"}


async def test_put_valid_config_saves(
    client_with_project_session: TestClient, session_tmp_path: Path
) -> None:
    """A valid config is saved to ert/model."""
    model_dir = _model_dir(session_tmp_path)
    with patch.object(ErtService, "validate", AsyncMock(return_value=VALID)):
        response = client_with_project_session.put(
            f"{ROUTE}/configs/new.ert", json={"content": "NUM_REALIZATIONS 1\n"}
        )
    assert response.status_code == status.HTTP_200_OK, response.json()
    assert (model_dir / "new.ert").read_text() == "NUM_REALIZATIONS 1\n"


async def test_put_invalid_config_not_saved(
    client_with_project_session: TestClient, session_tmp_path: Path
) -> None:
    """An invalid config returns 422 with the validation result."""
    model_dir = _model_dir(session_tmp_path)
    with patch.object(ErtService, "validate", AsyncMock(return_value=INVALID)):
        response = client_with_project_session.put(
            f"{ROUTE}/configs/new.ert", json={"content": "NUM_REALIZATIONS x\n"}
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()["detail"]["validation"] == INVALID.model_dump()
    assert not (model_dir / "new.ert").exists()


async def test_get_rms_projects(client_with_project_session: TestClient) -> None:
    """Returns RMS projects with detected versions."""
    projects = ErtRmsProjectList.model_validate(
        {"projects": [{"name": "drogon.rms14.2.2", "version": "14.2.2"}]}
    )
    with patch.object(ErtService, "list_rms_projects", return_value=projects):
        response = client_with_project_session.get(f"{ROUTE}/rms_projects")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "projects": [{"name": "drogon.rms14.2.2", "version": "14.2.2", "error": None}]
    }
