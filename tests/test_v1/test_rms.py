"""Tests for the RMS routes."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from fmu.settings.models.project_config import RmsHorizon, RmsStratigraphicZone, RmsWell
from runrms.api.proxy import RemoteException
from runrms.exceptions import RmsProjectNotFoundError, RmsVersionError

from fmu_settings_api.__main__ import app
from fmu_settings_api.deps.rms import (
    get_opened_rms_project,
    get_rms_project_path,
    get_rms_service,
)
from fmu_settings_api.deps.session import get_session_service
from fmu_settings_api.session import SessionNotFoundError

ROUTE = "/api/v1/rms"


async def test_open_rms_project_success(
    client_with_project_session: TestClient,
) -> None:
    """Test opening an RMS project successfully."""
    rms_version = "14.2.2"
    mock_service = MagicMock()
    mock_service.open_rms_project.return_value = (MagicMock(), MagicMock())
    mock_service.get_rms_version.return_value = rms_version
    rms_path = Path("/path/to/rms/project")

    app.dependency_overrides[get_rms_service] = lambda: mock_service
    app.dependency_overrides[get_rms_project_path] = lambda: rms_path

    response = client_with_project_session.post(f"{ROUTE}/")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "message": f"RMS project opened successfully with RMS version {rms_version}."
    }
    mock_service.open_rms_project.assert_called_once_with(rms_path, rms_version)


async def test_open_rms_project_with_specified_version(
    client_with_project_session: TestClient,
) -> None:
    """Test opening an RMS project with a specified RMS version."""
    default_rms_version = "14.2.2"
    specified_rms_version = "15.1.0.0"

    mock_service = MagicMock()
    mock_service.open_rms_project.return_value = (MagicMock(), MagicMock())
    mock_service.get_rms_version.return_value = default_rms_version

    rms_path = Path("/path/to/rms/project")

    app.dependency_overrides[get_rms_service] = lambda: mock_service
    app.dependency_overrides[get_rms_project_path] = lambda: rms_path

    response = client_with_project_session.post(
        ROUTE, json={"version": specified_rms_version}
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "message": (
            f"RMS project opened successfully with RMS version {specified_rms_version}."
        )
    }
    mock_service.get_rms_version.assert_not_called()
    mock_service.open_rms_project.assert_called_once_with(
        rms_path, specified_rms_version
    )


async def test_open_rms_project_without_specified_version(
    client_with_project_session: TestClient,
) -> None:
    """Test opening an RMS project without a specified RMS version."""
    default_rms_version = "14.2.2"

    mock_service = MagicMock()
    mock_service.open_rms_project.return_value = (MagicMock(), MagicMock())
    mock_service.get_rms_version.return_value = "14.2.2"
    rms_path = Path("/path/to/rms/project")

    app.dependency_overrides[get_rms_service] = lambda: mock_service
    app.dependency_overrides[get_rms_project_path] = lambda: rms_path

    response = client_with_project_session.post(f"{ROUTE}/")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "message": (
            f"RMS project opened successfully with RMS version {default_rms_version}."
        )
    }
    mock_service.get_rms_version.assert_called_once_with(rms_path)
    mock_service.open_rms_project.assert_called_once_with(rms_path, default_rms_version)


async def test_open_rms_project_no_session() -> None:
    """Test opening an RMS project without a valid session."""
    with TestClient(app) as client:
        response = client.post(f"{ROUTE}/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "No active session found"


async def test_open_rms_project_path_not_configured(
    client_with_project_session: TestClient,
) -> None:
    """Test opening an RMS project when path is not in config."""
    mock_service = MagicMock()
    app.dependency_overrides[get_rms_service] = lambda: mock_service

    def _raise_missing_path() -> Path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="RMS project path is not set in the project config file.",
        )

    app.dependency_overrides[get_rms_project_path] = _raise_missing_path

    response = client_with_project_session.post(f"{ROUTE}/")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "detail": "RMS project path is not set in the project config file."
    }


async def test_open_rms_project_not_found(
    client_with_project_session: TestClient,
) -> None:
    """Test opening an RMS project when the project directory does not exist."""
    mock_service = MagicMock()

    rms_path = Path("/nonexistent/path/to/project.rms14")
    mock_service.open_rms_project.side_effect = RmsProjectNotFoundError(
        f"The project: {rms_path} does not exist as a directory."
    )

    rms_version = "14.2.2"
    mock_service.get_rms_version.return_value = rms_version

    app.dependency_overrides[get_rms_service] = lambda: mock_service
    app.dependency_overrides[get_rms_project_path] = lambda: rms_path

    response = client_with_project_session.post(f"{ROUTE}/")

    mock_service.get_rms_version.assert_called_once_with(rms_path)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {
        "detail": (f"RMS project does not exist at the configured path: {rms_path}.")
    }


async def test_open_rms_project_unsupported_version(
    client_with_project_session: TestClient,
) -> None:
    """Tests opening an RMS project with an unsupported RMS version."""
    mock_service = MagicMock()
    specified_rms_version = "15.0.1.0"
    rms_path = Path("/path/to/rms/project")

    mock_service.open_rms_project.side_effect = RmsVersionError(
        f"RMS version {specified_rms_version} is not supported."
    )

    app.dependency_overrides[get_rms_service] = lambda: mock_service
    app.dependency_overrides[get_rms_project_path] = lambda: rms_path

    response = client_with_project_session.post(
        ROUTE, json={"version": specified_rms_version}
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {
        "detail": (
            f"Failed to open RMS project {rms_path}: Failed setting up RMS "
            f"API proxy: The requested RMS version {specified_rms_version} "
            "is not supported. Try specifying another RMS version "
            "or upgrading the RMS project."
        )
    }


async def test_open_rms_project_version_out_of_sync(
    client_with_project_session: TestClient,
) -> None:
    """Tests opening an RMS project with a version out of sync with the project."""
    mock_service = MagicMock()
    specified_rms_version = "15.0.1.0"
    rms_path = Path("/path/to/old/rms/project")

    remote_exception = RemoteException(
        message="File version xxxx.xxxx is not supported."
    )
    mock_service.open_rms_project.side_effect = remote_exception

    app.dependency_overrides[get_rms_service] = lambda: mock_service
    app.dependency_overrides[get_rms_project_path] = lambda: rms_path

    response = client_with_project_session.post(
        ROUTE, json={"version": specified_rms_version}
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {
        "detail": (
            f"Failed to open RMS project {rms_path}: Could not open project using "
            f"RMS version {specified_rms_version}: {str(remote_exception)}"
        )
    }


async def test_open_rms_project_licence_failure(
    client_with_project_session: TestClient,
) -> None:
    """Tests opening an RMS project when RMS API license check out fails."""
    mock_service = MagicMock()

    rms_path = Path("/path/to/rms/project")
    remote_exception = RemoteException(message="Unable to check out required license.")
    mock_service.open_rms_project.side_effect = remote_exception

    rms_version = "14.2.2"
    mock_service.get_rms_version.return_value = rms_version

    app.dependency_overrides[get_rms_service] = lambda: mock_service
    app.dependency_overrides[get_rms_project_path] = lambda: rms_path

    response = client_with_project_session.post(f"{ROUTE}/")

    mock_service.get_rms_version.assert_called_once_with(rms_path)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {
        "detail": (
            f"Failed to open RMS project {rms_path}: "
            f"Unable to check out required license: {str(remote_exception)}"
        )
    }


async def test_open_rms_project_remote_exception(
    client_with_project_session: TestClient,
) -> None:
    """Tests opening an RMS project with a failing request to RMS API Proxy."""
    mock_service = MagicMock()

    rms_path = Path("/path/to/rms/project")
    remote_exception = RemoteException(message="Some error message from the remote.")
    mock_service.open_rms_project.side_effect = remote_exception

    rms_version = "14.2.2"
    mock_service.get_rms_version.return_value = rms_version

    app.dependency_overrides[get_rms_service] = lambda: mock_service
    app.dependency_overrides[get_rms_project_path] = lambda: rms_path

    response = client_with_project_session.post(f"{ROUTE}/")

    mock_service.get_rms_version.assert_called_once_with(rms_path)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {
        "detail": (f"Failed to open RMS project {rms_path}: {str(remote_exception)}")
    }


async def test_open_rms_project_unexpected_service_error(
    client_with_project_session: TestClient,
) -> None:
    """Test handling of unexpected errors from the RMS service."""
    mock_service = MagicMock()
    mock_service.open_rms_project.side_effect = Exception("RMS service error.")

    app.dependency_overrides[get_rms_service] = lambda: mock_service
    app.dependency_overrides[get_rms_project_path] = lambda: Path()

    response = client_with_project_session.post(f"{ROUTE}/")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json() == {"detail": "An unexpected error occurred."}


async def test_close_rms_project_success(
    client_with_project_session: TestClient,
) -> None:
    """Test closing an RMS project successfully."""
    response = client_with_project_session.delete(f"{ROUTE}/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"message": "RMS project closed successfully"}


async def test_close_rms_project_no_session() -> None:
    """Test closing an RMS project without a valid session."""
    with TestClient(app) as client:
        response = client.delete(f"{ROUTE}/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "No active session found"


async def test_get_zones_success(
    client_with_project_session: TestClient,
) -> None:
    """Test getting zones successfully."""
    mock_service = MagicMock()
    mock_rms_project = MagicMock()
    expected_column = [
        RmsStratigraphicZone(
            name="Zone1", top_horizon_name="TopHorizon", base_horizon_name="BaseHorizon"
        ),
        RmsStratigraphicZone(
            name="Zone2",
            top_horizon_name="BaseHorizon",
            base_horizon_name="BottomHorizon",
        ),
    ]
    mock_service.get_zones.return_value = expected_column

    app.dependency_overrides[get_rms_service] = lambda: mock_service
    app.dependency_overrides[get_opened_rms_project] = lambda: mock_rms_project
    app.dependency_overrides[get_rms_project_path] = lambda: Path("/path/to/rms")

    response = client_with_project_session.get(f"{ROUTE}/zones")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [zone.model_dump() for zone in expected_column]
    mock_service.get_zones.assert_called_once_with(mock_rms_project)


async def test_get_zones_with_strat_columns(
    client_with_project_session: TestClient,
) -> None:
    """Test getting zones with stratigraphic columns."""
    mock_service = MagicMock()
    mock_rms_project = MagicMock()
    expected_zones = [
        RmsStratigraphicZone(
            name="Zone1",
            top_horizon_name="TopHorizon",
            base_horizon_name="BaseHorizon",
            stratigraphic_column_name=["Column1"],
        ),
        RmsStratigraphicZone(
            name="Zone2",
            top_horizon_name="BaseHorizon",
            base_horizon_name="BottomHorizon",
            stratigraphic_column_name=["Column1"],
        ),
        RmsStratigraphicZone(
            name="Zone3",
            top_horizon_name="BottomHorizon",
            base_horizon_name="DeepHorizon",
            stratigraphic_column_name=["Column1"],
        ),
    ]
    mock_service.get_zones.return_value = expected_zones

    app.dependency_overrides[get_rms_service] = lambda: mock_service
    app.dependency_overrides[get_opened_rms_project] = lambda: mock_rms_project
    app.dependency_overrides[get_rms_project_path] = lambda: Path("/path/to/rms")

    response = client_with_project_session.get(f"{ROUTE}/zones")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [zone.model_dump() for zone in expected_zones]
    mock_service.get_zones.assert_called_once_with(mock_rms_project)


async def test_get_zones_no_project_open(
    client_with_project_session: TestClient,
) -> None:
    """Test getting zones when no project is open."""
    response = client_with_project_session.get(f"{ROUTE}/zones")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "detail": "No RMS project is currently open. Please open an RMS project first."
    }


async def test_get_horizons_success(
    client_with_project_session: TestClient,
) -> None:
    """Test getting horizons successfully."""
    mock_service = MagicMock()
    mock_rms_project = MagicMock()
    expected_horizons = [
        RmsHorizon(name="TopHorizon", type="calculated"),
        RmsHorizon(name="BaseHorizon", type="interpreted"),
        RmsHorizon(name="BottomHorizon", type="calculated"),
    ]
    mock_service.get_horizons.return_value = expected_horizons

    app.dependency_overrides[get_rms_service] = lambda: mock_service
    app.dependency_overrides[get_opened_rms_project] = lambda: mock_rms_project

    response = client_with_project_session.get(f"{ROUTE}/horizons")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [horizon.model_dump() for horizon in expected_horizons]
    mock_service.get_horizons.assert_called_once_with(mock_rms_project)


async def test_get_horizons_no_project_open(
    client_with_project_session: TestClient,
) -> None:
    """Test getting horizons when no project is open."""
    response = client_with_project_session.get(f"{ROUTE}/horizons")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "detail": "No RMS project is currently open. Please open an RMS project first."
    }


async def test_get_wells_success(
    client_with_project_session: TestClient,
) -> None:
    """Test getting wells successfully."""
    mock_service = MagicMock()
    mock_rms_project = MagicMock()
    expected_wells = [
        RmsWell(name="Well_A"),
        RmsWell(name="Well_B"),
        RmsWell(name="Well_C"),
    ]
    mock_service.get_wells.return_value = expected_wells

    app.dependency_overrides[get_rms_service] = lambda: mock_service
    app.dependency_overrides[get_opened_rms_project] = lambda: mock_rms_project

    response = client_with_project_session.get(f"{ROUTE}/wells")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [well.model_dump() for well in expected_wells]
    mock_service.get_wells.assert_called_once_with(mock_rms_project)


async def test_get_wells_no_project_open(
    client_with_project_session: TestClient,
) -> None:
    """Test getting wells when no project is open."""
    response = client_with_project_session.get(f"{ROUTE}/wells")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "detail": "No RMS project is currently open. Please open an RMS project first."
    }


async def test_open_rms_project_session_not_found(
    client_with_project_session: TestClient,
) -> None:
    """Test opening an RMS project when session is not found during add."""
    mock_rms_service = MagicMock()
    mock_rms_service.open_rms_project.return_value = (MagicMock(), MagicMock())
    rms_path = Path("/path/to/rms/project")

    mock_session_service = AsyncMock()
    mock_session_service.add_rms_session = AsyncMock(
        side_effect=SessionNotFoundError("Session not found")
    )

    app.dependency_overrides[get_rms_service] = lambda: mock_rms_service
    app.dependency_overrides[get_rms_project_path] = lambda: rms_path
    app.dependency_overrides[get_session_service] = lambda: mock_session_service

    response = client_with_project_session.post(f"{ROUTE}/")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Session not found"


async def test_close_rms_project_session_not_found(
    client_with_project_session: TestClient,
) -> None:
    """Test closing an RMS project when session is not found."""
    mock_session_service = MagicMock()
    mock_session_service.remove_rms_session = AsyncMock(
        side_effect=SessionNotFoundError("Session not found")
    )
    app.dependency_overrides[get_session_service] = lambda: mock_session_service

    response = client_with_project_session.delete(f"{ROUTE}/")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Session not found"


async def test_close_rms_project_generic_error(
    client_with_project_session: TestClient,
) -> None:
    """Test closing an RMS project when a generic error occurs."""
    mock_session_service = MagicMock()
    mock_session_service.remove_rms_session = AsyncMock(
        side_effect=Exception("Unexpected error")
    )
    app.dependency_overrides[get_session_service] = lambda: mock_session_service

    response = client_with_project_session.delete(f"{ROUTE}/")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["detail"] == "An unexpected error occurred."


async def test_get_zones_service_error(
    client_with_project_session: TestClient,
) -> None:
    """Test getting zones when service raises an error."""
    mock_service = MagicMock()
    mock_service.get_zones.side_effect = Exception("Service error")

    app.dependency_overrides[get_rms_service] = lambda: mock_service
    app.dependency_overrides[get_opened_rms_project] = lambda: MagicMock()
    app.dependency_overrides[get_rms_project_path] = lambda: Path("/path/to/rms")

    response = client_with_project_session.get(f"{ROUTE}/zones")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["detail"] == "An unexpected error occurred."


async def test_get_horizons_service_error(
    client_with_project_session: TestClient,
) -> None:
    """Test getting horizons when service raises an error."""
    mock_service = MagicMock()
    mock_service.get_horizons.side_effect = Exception("Service error")

    app.dependency_overrides[get_rms_service] = lambda: mock_service
    app.dependency_overrides[get_opened_rms_project] = lambda: MagicMock()

    response = client_with_project_session.get(f"{ROUTE}/horizons")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["detail"] == "An unexpected error occurred."


async def test_get_wells_service_error(
    client_with_project_session: TestClient,
) -> None:
    """Test getting wells when service raises an error."""
    mock_service = MagicMock()
    mock_service.get_wells.side_effect = Exception("Service error")

    app.dependency_overrides[get_rms_service] = lambda: mock_service
    app.dependency_overrides[get_opened_rms_project] = lambda: MagicMock()

    response = client_with_project_session.get(f"{ROUTE}/wells")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["detail"] == "An unexpected error occurred."


async def test_get_coordinate_system_success(
    client_with_project_session: TestClient,
) -> None:
    """Test getting coordinate system successfully."""
    mock_service = MagicMock()
    mock_rms_project = MagicMock()
    expected_coord_system = {"name": "westeros"}
    mock_service.get_coordinate_system.return_value = expected_coord_system

    app.dependency_overrides[get_rms_service] = lambda: mock_service
    app.dependency_overrides[get_opened_rms_project] = lambda: mock_rms_project

    response = client_with_project_session.get(f"{ROUTE}/coordinate_system")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == expected_coord_system
    mock_service.get_coordinate_system.assert_called_once_with(mock_rms_project)


async def test_get_coordinate_system_no_project_open(
    client_with_project_session: TestClient,
) -> None:
    """Test getting coordinate system when no project is open."""
    response = client_with_project_session.get(f"{ROUTE}/coordinate_system")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "detail": "No RMS project is currently open. Please open an RMS project first."
    }


async def test_get_coordinate_system_service_error(
    client_with_project_session: TestClient,
) -> None:
    """Test getting coordinate system when service raises an error."""
    mock_service = MagicMock()
    mock_service.get_coordinate_system.side_effect = Exception("Service error")

    app.dependency_overrides[get_rms_service] = lambda: mock_service
    app.dependency_overrides[get_opened_rms_project] = lambda: MagicMock()

    response = client_with_project_session.get(f"{ROUTE}/coordinate_system")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["detail"] == "An unexpected error occurred."
