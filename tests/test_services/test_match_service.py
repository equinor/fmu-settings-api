"""Tests for the MatchService."""

from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fmu.datamodels.common.masterdata import CoordinateSystem
from fmu.settings.models.project_config import RmsCoordinateSystem, RmsStratigraphicZone
from httpx import HTTPStatusError, Request, Response

from fmu_settings_api.models.match import RmsCoordinateSystemMatch
from fmu_settings_api.models.smda import SmdaStratigraphicUnitsResult, StratigraphicUnit
from fmu_settings_api.services.match import MatchService


@pytest.fixture
def match_service() -> MatchService:
    """Returns a MatchService instance."""
    return MatchService()


@pytest.fixture
def mock_project_session() -> MagicMock:
    """Returns a mock ProjectSession."""
    session = MagicMock()
    session.project_fmu_directory.get_config_value = MagicMock()
    return session


@pytest.fixture
def mock_smda_service() -> AsyncMock:
    """Returns a mock SmdaService."""
    return AsyncMock()


class TestMatchZonesToUnits:
    """Tests for match_zones_to_units method."""

    def test_perfect_match(
        self,
        match_service: MatchService,
        create_stratigraphic_unit: Callable[..., StratigraphicUnit],
    ) -> None:
        """Test matching with identical names returns 100 score."""
        rms_zones = [
            RmsStratigraphicZone(
                name="Viking GP", top_horizon_name="Top", base_horizon_name="Base"
            ),
        ]
        smda_units = [
            create_stratigraphic_unit("Viking GP"),
        ]

        matches = match_service.match_stratigraphy(rms_zones, smda_units)

        assert len(matches) == 1
        assert matches[0].rms_zone.name == "Viking GP"
        assert matches[0].smda_unit.identifier == "Viking GP"
        assert matches[0].score == 100.0  # noqa: PLR2004
        assert matches[0].confidence == "high"

    def test_token_reordering(
        self,
        match_service: MatchService,
        create_stratigraphic_unit: Callable[..., StratigraphicUnit],
    ) -> None:
        """Test matching handles token order differences."""
        rms_zones = [
            RmsStratigraphicZone(
                name="Viking GP", top_horizon_name="Top", base_horizon_name="Base"
            ),
        ]
        smda_units = [
            create_stratigraphic_unit("GP Viking"),
        ]

        matches = match_service.match_stratigraphy(rms_zones, smda_units)

        assert len(matches) == 1
        assert matches[0].score == 100  # noqa: PLR2004
        assert matches[0].confidence in ["medium", "high"]

    def test_name_normalization(
        self,
        match_service: MatchService,
        create_stratigraphic_unit: Callable[..., StratigraphicUnit],
    ) -> None:
        """Test that names are normalized (lowercase, underscores, dots)."""
        rms_zones = [
            RmsStratigraphicZone(
                name="Viking_GP.2.1", top_horizon_name="Top", base_horizon_name="Base"
            ),
        ]
        smda_units = [
            create_stratigraphic_unit("VIKING GP 2 1"),
        ]

        matches = match_service.match_stratigraphy(rms_zones, smda_units)

        assert len(matches) == 1
        assert matches[0].score == 100.0  # noqa: PLR2004
        assert matches[0].confidence == "high"

    def test_greedy_matching_each_zone_gets_best_match(
        self,
        match_service: MatchService,
        create_stratigraphic_unit: Callable[..., StratigraphicUnit],
    ) -> None:
        """Test that greedy algorithm assigns each zone to its best matching unit."""
        rms_zones = [
            RmsStratigraphicZone(
                name="Viking GP", top_horizon_name="Top", base_horizon_name="Base"
            ),
            RmsStratigraphicZone(
                name="Tarbert Fm", top_horizon_name="Top", base_horizon_name="Base"
            ),
        ]
        smda_units = [
            create_stratigraphic_unit("Viking Group"),
            create_stratigraphic_unit("Tarbert Formation"),
            create_stratigraphic_unit("Unrelated Unit"),
        ]

        matches = match_service.match_stratigraphy(rms_zones, smda_units)

        assert len(matches) == 2  # noqa: PLR2004
        # Viking GP should match Viking Group
        assert matches[0].rms_zone.name == "Viking GP"
        assert "Viking" in matches[0].smda_unit.identifier
        # Tarbert Fm should match Tarbert Formation
        assert matches[1].rms_zone.name == "Tarbert Fm"
        assert "Tarbert" in matches[1].smda_unit.identifier

    def test_empty_rms_zones(
        self,
        match_service: MatchService,
        create_stratigraphic_unit: Callable[..., StratigraphicUnit],
    ) -> None:
        """Test matching with empty RMS zones returns empty list."""
        rms_zones: list[RmsStratigraphicZone] = []
        smda_units = [
            create_stratigraphic_unit("Viking GP"),
        ]

        matches = match_service.match_stratigraphy(rms_zones, smda_units)

        assert matches == []

    def test_empty_smda_units(
        self,
        match_service: MatchService,
        create_stratigraphic_unit: Callable[..., StratigraphicUnit],
    ) -> None:
        """Test matching with empty SMDA units returns empty list."""
        rms_zones = [
            RmsStratigraphicZone(
                name="Viking GP", top_horizon_name="Top", base_horizon_name="Base"
            ),
        ]
        smda_units: list[StratigraphicUnit] = []

        matches = match_service.match_stratigraphy(rms_zones, smda_units)

        assert matches == []

    def test_multiple_zones_preserved_order(
        self,
        match_service: MatchService,
        create_stratigraphic_unit: Callable[..., StratigraphicUnit],
    ) -> None:
        """Test that matching preserves the original zone order."""
        rms_zones = [
            RmsStratigraphicZone(
                name="Zone A", top_horizon_name="Top", base_horizon_name="Base"
            ),
            RmsStratigraphicZone(
                name="Zone B", top_horizon_name="Top", base_horizon_name="Base"
            ),
            RmsStratigraphicZone(
                name="Zone C", top_horizon_name="Top", base_horizon_name="Base"
            ),
        ]
        smda_units = [
            create_stratigraphic_unit("Unit A"),
            create_stratigraphic_unit("Unit B"),
            create_stratigraphic_unit("Unit C"),
        ]

        matches = match_service.match_stratigraphy(rms_zones, smda_units)

        assert len(matches) == 3  # noqa: PLR2004
        assert matches[0].rms_zone.name == "Zone A"
        assert matches[1].rms_zone.name == "Zone B"
        assert matches[2].rms_zone.name == "Zone C"


class TestMatchCoordinateSystems:
    """Tests for match_coordinate_system method."""

    def test_exact_match(self, match_service: MatchService) -> None:
        """Test coordinate system matching with exact names."""
        rms_crs = RmsCoordinateSystem(name="ED50 UTM31")
        smda_crs = CoordinateSystem(identifier="ED50 UTM31", uuid=uuid4())

        match = match_service.match_coordinate_system(rms_crs, smda_crs)

        assert isinstance(match, RmsCoordinateSystemMatch)
        assert match.rms_crs_sys.name == "ED50 UTM31"
        assert match.smda_crs_sys.identifier == "ED50 UTM31"
        assert match.score == 100.0  # noqa: PLR2004
        assert match.confidence == "high"

    def test_partial_match_medium_confidence(self, match_service: MatchService) -> None:
        """Test coordinate system matching with similar names."""
        rms_crs = RmsCoordinateSystem(name="ED50 UTM Zone 31")
        smda_crs = CoordinateSystem(identifier="ED50 UTM31", uuid=uuid4())

        match = match_service.match_coordinate_system(rms_crs, smda_crs)

        assert 50 <= match.score <= 80  # noqa: PLR2004
        assert match.confidence == "medium"

    def test_low_confidence_match(self, match_service: MatchService) -> None:
        """Test matching with very different names returns low confidence."""
        rms_crs = RmsCoordinateSystem(name="ED50")
        smda_crs = CoordinateSystem(identifier="WGS84 UTM Zone 32", uuid=uuid4())

        match = match_service.match_coordinate_system(rms_crs, smda_crs)

        assert match.score < 50  # noqa: PLR2004
        assert match.confidence == "low"

    def test_normalization(self, match_service: MatchService) -> None:
        """Test that coordinate system names are normalized."""
        rms_crs = RmsCoordinateSystem(name="ED50_UTM.31")
        smda_crs = CoordinateSystem(identifier="ED50 UTM 31", uuid=uuid4())

        match = match_service.match_coordinate_system(rms_crs, smda_crs)

        assert match.score == 100.0  # noqa: PLR2004
        assert match.confidence == "high"


class TestMatchStratigraphyFromConfigToSmda:
    """Tests for match_stratigraphy_from_config_to_smda method."""

    async def test_success(
        self,
        match_service: MatchService,
        mock_project_session: MagicMock,
        mock_smda_service: AsyncMock,
        create_stratigraphic_unit: Callable[..., StratigraphicUnit],
    ) -> None:
        """Test successful matching from config to SMDA."""
        mock_project_session.project_fmu_directory.get_config_value.side_effect = (
            lambda key, default: {
                "rms.zones": [
                    {
                        "name": "Viking GP",
                        "top_horizon_name": "Top",
                        "base_horizon_name": "Base",
                    }
                ],
                "masterdata.smda.stratigraphic_column.identifier": "NSO_SP_1984",
            }.get(key, default)
        )

        smda_units = [create_stratigraphic_unit("Viking Group")]
        mock_smda_service.get_stratigraphic_units.return_value = (
            SmdaStratigraphicUnitsResult(stratigraphic_units=smda_units)
        )

        matches = await match_service.match_stratigraphy_from_config_to_smda(
            mock_project_session, mock_smda_service
        )

        assert len(matches) == 1
        assert matches[0].rms_zone.name == "Viking GP"
        assert matches[0].smda_unit.identifier == "Viking Group"
        mock_smda_service.get_stratigraphic_units.assert_called_once_with("NSO_SP_1984")

    async def test_missing_rms_zones_config(
        self,
        match_service: MatchService,
        mock_project_session: MagicMock,
        mock_smda_service: AsyncMock,
    ) -> None:
        """Test ValueError when rms.zones is missing from config."""
        mock_project_session.project_fmu_directory.get_config_value.return_value = None

        with pytest.raises(ValueError, match="No RMS zones found in project config"):
            await match_service.match_stratigraphy_from_config_to_smda(
                mock_project_session, mock_smda_service
            )

    async def test_missing_stratigraphic_column_identifier(
        self,
        match_service: MatchService,
        mock_project_session: MagicMock,
        mock_smda_service: AsyncMock,
    ) -> None:
        """Test ValueError when stratigraphic column identifier is missing."""
        mock_project_session.project_fmu_directory.get_config_value.side_effect = (
            lambda key, default: {
                "rms.zones": [
                    {
                        "name": "Viking GP",
                        "top_horizon_name": "Top",
                        "base_horizon_name": "Base",
                    }
                ],
            }.get(key, default)
        )

        with pytest.raises(
            ValueError, match="No stratigraphic column identifier found"
        ):
            await match_service.match_stratigraphy_from_config_to_smda(
                mock_project_session, mock_smda_service
            )

    @pytest.mark.parametrize(
        ("error_type", "error_instance"),
        [
            (
                HTTPStatusError,
                HTTPStatusError(
                    "404 Not Found",
                    request=Request("GET", "http://smda.com"),
                    response=Response(404),
                ),
            ),
            (KeyError, KeyError("malformed response")),
            (TimeoutError, TimeoutError("Request timeout")),
        ],
    )
    async def test_propagates_smda_errors(
        self,
        match_service: MatchService,
        mock_project_session: MagicMock,
        mock_smda_service: AsyncMock,
        error_type: type[Exception],
        error_instance: Exception,
    ) -> None:
        """Test that errors from SMDA service are propagated."""
        mock_project_session.project_fmu_directory.get_config_value.side_effect = (
            lambda key, default: {
                "rms.zones": [
                    {
                        "name": "Viking GP",
                        "top_horizon_name": "Top",
                        "base_horizon_name": "Base",
                    }
                ],
                "masterdata.smda.stratigraphic_column.identifier": "NSO_SP_1984",
            }.get(key, default)
        )

        mock_smda_service.get_stratigraphic_units.side_effect = error_instance

        with pytest.raises(error_type):
            await match_service.match_stratigraphy_from_config_to_smda(
                mock_project_session, mock_smda_service
            )


class TestMatchCoordinateSystemFromConfig:
    """Tests for match_coordinate_system_from_config_to_smda method."""

    def test_success(
        self, match_service: MatchService, mock_project_session: MagicMock
    ) -> None:
        """Test successful coordinate system matching from config."""
        mock_project_session.project_fmu_directory.get_config_value.side_effect = (
            lambda key, default: {
                "rms.coordinate_system": {
                    "name": "ED50 UTM31",
                    "projection": "utm",
                    "datum": "ED50",
                },
                "masterdata.smda.coordinate_system": {
                    "identifier": "ED50 UTM31",
                    "uuid": str(uuid4()),
                },
            }.get(key, default)
        )

        match = match_service.match_coordinate_system_from_config_to_smda(
            mock_project_session
        )

        assert isinstance(match, RmsCoordinateSystemMatch)
        assert match.rms_crs_sys.name == "ED50 UTM31"
        assert match.smda_crs_sys.identifier == "ED50 UTM31"
        assert match.score == 100.0  # noqa: PLR2004
        assert match.confidence == "high"

    def test_missing_rms_coordinate_system(
        self, match_service: MatchService, mock_project_session: MagicMock
    ) -> None:
        """Test ValueError when rms.coordinate_system is missing."""
        mock_project_session.project_fmu_directory.get_config_value.return_value = None

        with pytest.raises(
            ValueError, match="No RMS coordinate system found in project config"
        ):
            match_service.match_coordinate_system_from_config_to_smda(
                mock_project_session
            )

    def test_missing_smda_coordinate_system(
        self, match_service: MatchService, mock_project_session: MagicMock
    ) -> None:
        """Test ValueError when smda.coordinate_system is missing."""
        mock_project_session.project_fmu_directory.get_config_value.side_effect = (
            lambda key, default: {
                "rms.coordinate_system": {
                    "name": "ED50 UTM31",
                    "projection": "utm",
                    "datum": "ED50",
                },
            }.get(key, default)
        )

        with pytest.raises(
            ValueError, match="No SMDA coordinate system found in project masterdata"
        ):
            match_service.match_coordinate_system_from_config_to_smda(
                mock_project_session
            )
