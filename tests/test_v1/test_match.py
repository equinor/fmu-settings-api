"""Tests for the /api/v1/match routes."""

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from fmu_settings_api.__main__ import app

ROUTE = "/api/v1/match"
PERFECT_MATCH_SCORE = 100.0


class TestPostMatchEndpoint:
    """Tests for POST /api/v1/match endpoint."""

    def test_successful_match(self) -> None:
        """Test successful matching returns grouped match results."""
        with TestClient(app) as client:
            response = client.post(
                ROUTE,
                json={
                    "sources": ["Viking GP"],
                    "targets": ["Viking Group"],
                    "replacements": [{"original": "GP", "replacement": "Group"}],
                },
            )

        assert response.status_code == status.HTTP_200_OK, response.json()
        assert response.json() == [
            {
                "source": "Viking GP",
                "matches": [
                    {
                        "target": "Viking Group",
                        "score": 100.0,
                        "confidence": "high",
                    }
                ],
            }
        ]

    def test_replacements_are_optional(self) -> None:
        """Test matching succeeds when replacements are omitted."""
        with TestClient(app) as client:
            response = client.post(
                ROUTE,
                json={
                    "sources": ["Viking-GP"],
                    "targets": ["Viking GP"],
                },
            )

        assert response.status_code == status.HTTP_200_OK, response.json()
        assert response.json()[0]["matches"][0]["score"] == PERFECT_MATCH_SCORE

    def test_empty_targets_returns_source_with_empty_matches(self) -> None:
        """Test matching with no targets returns source with no matches."""
        with TestClient(app) as client:
            response = client.post(
                ROUTE,
                json={
                    "sources": ["Viking GP"],
                    "targets": [],
                },
            )

        assert response.status_code == status.HTTP_200_OK, response.json()
        assert response.json() == [{"source": "Viking GP", "matches": []}]

    def test_invalid_payload_returns_validation_error(self) -> None:
        """Test invalid request body returns 422."""
        with TestClient(app) as client:
            response = client.post(
                ROUTE,
                json={
                    "sources": "Viking GP",
                    "targets": ["Viking GP"],
                },
            )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.parametrize("original", ["", "_"])
    def test_empty_replacement_original_returns_validation_error(
        self, original: str
    ) -> None:
        """Test replacement rules must have a useful original value."""
        with TestClient(app) as client:
            response = client.post(
                ROUTE,
                json={
                    "sources": ["Viking GP"],
                    "targets": ["Viking Group"],
                    "replacements": [{"original": original, "replacement": "Group"}],
                },
            )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        error_message = response.json()["detail"][0]["msg"]
        assert "Original must include text after normalization" in error_message
        assert 'separators such as "_", ".", "-", and "/"' in error_message
        assert '"Fm" -> "Formation"' in error_message
