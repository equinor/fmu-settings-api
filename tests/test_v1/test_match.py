"""Tests for the /api/v1/match routes."""

from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
from fastapi import status
from fastapi.testclient import TestClient
from fmu.datamodels.common.masterdata import CoordinateSystem
from fmu.settings.models.project_config import RmsCoordinateSystem, RmsStratigraphicZone

from fmu_settings_api.__main__ import app
from fmu_settings_api.config import HttpHeader
from fmu_settings_api.deps.match import get_match_service
from fmu_settings_api.deps.smda import get_project_smda_service
from fmu_settings_api.models.match import (
    RmsCoordinateSystemMatch,
    RmsStratigraphyMatch,
)
from fmu_settings_api.models.smda import StratigraphicUnit

ROUTE = "/api/v1/match"


class TestGetStratigraphyEndpoint:
    """Tests for GET /api/v1/match/stratigraphy endpoint."""

    def test_no_session(self) -> None:
        """Test 401 when no session is active."""
        with TestClient(app) as client:
            response = client.get(f"{ROUTE}/stratigraphy")
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            assert response.json()["detail"] == "No active session found"

    async def test_success(
        self,
        client_with_smda_session: TestClient,
        create_stratigraphic_unit: Callable[..., StratigraphicUnit],
    ) -> None:
        """Test successful stratigraphy matching."""
        mock_match_service = AsyncMock()
        mock_smda_service = AsyncMock()

        expected_matches = [
            RmsStratigraphyMatch(
                rms_zone=RmsStratigraphicZone(
                    name="Viking GP",
                    top_horizon_name="Top",
                    base_horizon_name="Base",
                ),
                smda_unit=create_stratigraphic_unit("Viking Group"),
                score=85.0,
                confidence="high",
            )
        ]
        mock_match_service.match_stratigraphy_from_config_to_smda.return_value = (
            expected_matches
        )

        app.dependency_overrides[get_match_service] = lambda: mock_match_service
        app.dependency_overrides[get_project_smda_service] = lambda: mock_smda_service

        response = client_with_smda_session.get(f"{ROUTE}/stratigraphy")

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert len(result) == 1
        assert result[0]["rms_zone"]["name"] == "Viking GP"
        assert result[0]["smda_unit"]["identifier"] == "Viking Group"
        assert result[0]["score"] == 85.0  # noqa: PLR2004
        assert result[0]["confidence"] == "high"

    async def test_missing_rms_zones_config(
        self, client_with_smda_session: TestClient
    ) -> None:
        """Test 400 when rms.zones config is missing."""
        mock_match_service = AsyncMock()
        mock_smda_service = AsyncMock()

        mock_match_service.match_stratigraphy_from_config_to_smda.side_effect = (
            ValueError("No RMS zones found in project config")
        )

        app.dependency_overrides[get_match_service] = lambda: mock_match_service
        app.dependency_overrides[get_project_smda_service] = lambda: mock_smda_service

        response = client_with_smda_session.get(f"{ROUTE}/stratigraphy")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "No RMS zones found in project config" in response.json()["detail"]

    async def test_missing_stratigraphic_column_identifier(
        self, client_with_smda_session: TestClient
    ) -> None:
        """Test 400 when stratigraphic column identifier is missing."""
        mock_match_service = AsyncMock()
        mock_smda_service = AsyncMock()

        mock_match_service.match_stratigraphy_from_config_to_smda.side_effect = (
            ValueError("No stratigraphic column identifier found")
        )

        app.dependency_overrides[get_match_service] = lambda: mock_match_service
        app.dependency_overrides[get_project_smda_service] = lambda: mock_smda_service

        response = client_with_smda_session.get(f"{ROUTE}/stratigraphy")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "No stratigraphic column identifier found" in response.json()["detail"]

    async def test_no_stratigraphic_units_found(
        self, client_with_smda_session: TestClient
    ) -> None:
        """Test 200 with empty list when no stratigraphic units found for matching."""
        mock_match_service = AsyncMock()
        mock_smda_service = AsyncMock()

        mock_match_service.match_stratigraphy_from_config_to_smda.return_value = []

        app.dependency_overrides[get_match_service] = lambda: mock_match_service
        app.dependency_overrides[get_project_smda_service] = lambda: mock_smda_service

        response = client_with_smda_session.get(f"{ROUTE}/stratigraphy")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    async def test_smda_http_error(self, client_with_smda_session: TestClient) -> None:
        """Test that SMDA HTTPStatusError is properly propagated."""
        mock_match_service = AsyncMock()
        mock_smda_service = AsyncMock()

        mock_request = MagicMock(spec=httpx.Request)
        mock_request.url = "https://smda.example.com/endpoint"
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404

        mock_match_service.match_stratigraphy_from_config_to_smda.side_effect = (
            httpx.HTTPStatusError(
                "404 Not Found",
                request=mock_request,
                response=mock_response,
            )
        )

        app.dependency_overrides[get_match_service] = lambda: mock_match_service
        app.dependency_overrides[get_project_smda_service] = lambda: mock_smda_service

        response = client_with_smda_session.get(f"{ROUTE}/stratigraphy")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert (
            response.headers[HttpHeader.UPSTREAM_SOURCE_KEY]
            == HttpHeader.UPSTREAM_SOURCE_SMDA
        )

    async def test_smda_malformed_response(
        self, client_with_smda_session: TestClient
    ) -> None:
        """Test 500 when SMDA returns malformed response."""
        mock_match_service = AsyncMock()
        mock_smda_service = AsyncMock()

        mock_match_service.match_stratigraphy_from_config_to_smda.side_effect = (
            KeyError("stratigraphic_units")
        )

        app.dependency_overrides[get_match_service] = lambda: mock_match_service
        app.dependency_overrides[get_project_smda_service] = lambda: mock_smda_service

        response = client_with_smda_session.get(f"{ROUTE}/stratigraphy")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert (
            response.headers[HttpHeader.UPSTREAM_SOURCE_KEY]
            == HttpHeader.UPSTREAM_SOURCE_SMDA
        )
        assert "Malformed response from SMDA" in response.json()["detail"]

    async def test_smda_timeout(self, client_with_smda_session: TestClient) -> None:
        """Test 503 when SMDA request times out."""
        mock_match_service = AsyncMock()
        mock_smda_service = AsyncMock()

        mock_match_service.match_stratigraphy_from_config_to_smda.side_effect = (
            TimeoutError("Request timed out")
        )

        app.dependency_overrides[get_match_service] = lambda: mock_match_service
        app.dependency_overrides[get_project_smda_service] = lambda: mock_smda_service

        response = client_with_smda_session.get(f"{ROUTE}/stratigraphy")

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert (
            response.headers[HttpHeader.UPSTREAM_SOURCE_KEY]
            == HttpHeader.UPSTREAM_SOURCE_SMDA
        )
        assert "timed out" in response.json()["detail"]


class TestGetCoordinateSystemEndpoint:
    """Tests for GET /api/v1/match/coordinate_system endpoint."""

    def test_no_session(self) -> None:
        """Test 401 when no session is active."""
        with TestClient(app) as client:
            response = client.get(f"{ROUTE}/coordinate_system")
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            assert response.json()["detail"] == "No active session found"

    async def test_success(self, client_with_project_session: TestClient) -> None:
        """Test successful coordinate system matching."""
        mock_match_service = MagicMock()

        expected_match = RmsCoordinateSystemMatch(
            rms_crs_sys=RmsCoordinateSystem(name="ED50 UTM31"),
            smda_crs_sys=CoordinateSystem(identifier="ED50 UTM31", uuid=uuid4()),
            score=100.0,
            confidence="high",
        )
        mock_match_service.match_coordinate_system_from_config_to_smda.return_value = (
            expected_match
        )

        app.dependency_overrides[get_match_service] = lambda: mock_match_service

        response = client_with_project_session.get(f"{ROUTE}/coordinate_system")

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["rms_crs_sys"]["name"] == "ED50 UTM31"
        assert result["smda_crs_sys"]["identifier"] == "ED50 UTM31"
        assert result["score"] == 100.0  # noqa: PLR2004
        assert result["confidence"] == "high"

    async def test_missing_rms_coordinate_system(
        self, client_with_project_session: TestClient
    ) -> None:
        """Test 400 when rms.coordinate_system config is missing."""
        mock_match_service = MagicMock()

        mock_match_service.match_coordinate_system_from_config_to_smda.side_effect = (
            ValueError("No RMS coordinate system found in project config")
        )

        app.dependency_overrides[get_match_service] = lambda: mock_match_service

        response = client_with_project_session.get(f"{ROUTE}/coordinate_system")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "No RMS coordinate system found" in response.json()["detail"]

    async def test_missing_smda_coordinate_system(
        self, client_with_project_session: TestClient
    ) -> None:
        """Test 400 when smda coordinate system is missing from masterdata."""
        mock_match_service = MagicMock()

        mock_match_service.match_coordinate_system_from_config_to_smda.side_effect = (
            ValueError("No SMDA coordinate system found in project masterdata")
        )

        app.dependency_overrides[get_match_service] = lambda: mock_match_service

        response = client_with_project_session.get(f"{ROUTE}/coordinate_system")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "No SMDA coordinate system found" in response.json()["detail"]
