"""Service for matching two different entities."""

import re
from typing import TYPE_CHECKING, Literal

from fmu.datamodels.common.masterdata import CoordinateSystem
from fmu.settings.models.project_config import RmsCoordinateSystem, RmsStratigraphicZone
from rapidfuzz import fuzz

from fmu_settings_api.models.match import (
    RmsCoordinateSystemMatch,
    RmsStratigraphyMatch,
)
from fmu_settings_api.models.smda import StratigraphicUnit

if TYPE_CHECKING:
    from fmu_settings_api.services.smda import SmdaService
    from fmu_settings_api.session import ProjectSession

HIGH_CONFIDENCE_THRESHOLD = 80
MEDIUM_CONFIDENCE_THRESHOLD = 50


class MatchService:
    """Service for matching two different entities."""

    async def match_stratigraphy_from_config_to_smda(
        self,
        project_session: "ProjectSession",
        smda_service: "SmdaService",
    ) -> list[RmsStratigraphyMatch]:
        """Match RMS zones from project config to SMDA stratigraphic units.

        This is a convenience method that:
        1. Fetches RMS zones from project config (rms.zones)
        2. Fetches stratigraphic column identifier from masterdata
        3. Queries SMDA for stratigraphic units
        4. Performs the matching using match_stratigraphy()

        Args:
            project_session: Session service with project configuration access
            smda_service: SMDA service for querying stratigraphic units

        Returns:
            List of RmsStratigraphyMatch objects

        Raises:
            ValueError: If config values are missing or invalid
            httpx.HTTPStatusError: If SMDA API request fails
            KeyError: If SMDA response is malformed
            TimeoutError: If SMDA API request times out
        """
        rms_zones_config = project_session.project_fmu_directory.get_config_value(
            "rms.zones", None
        )

        if not rms_zones_config:
            raise ValueError(
                "No RMS zones found in project config. "
                "Please configure rms.zones in the project config."
            )

        rms_zones = [RmsStratigraphicZone.model_validate(z) for z in rms_zones_config]

        strat_column_identifier = (
            project_session.project_fmu_directory.get_config_value(
                "masterdata.smda.stratigraphic_column.identifier", None
            )
        )

        if not strat_column_identifier:
            raise ValueError(
                "No stratigraphic column identifier found in project masterdata. "
                "Please configure masterdata.smda.stratigraphic_column.identifier "
                "in the project config."
            )

        smda_units_result = await smda_service.get_stratigraphic_units(
            strat_column_identifier
        )

        return self.match_stratigraphy(rms_zones, smda_units_result.stratigraphic_units)

    def match_coordinate_system_from_config_to_smda(
        self,
        project_session: "ProjectSession",
    ) -> RmsCoordinateSystemMatch:
        """Match RMS coordinate system to SMDA coordinate system from project config.

        This is a convenience method that:
        1. Fetches RMS coordinate system from project config (rms.coordinate_system)
        2. Fetches SMDA coordinate system from masterdata
        3. Performs the matching using match_coordinate_system()

        Args:
            project_session: Session service with project configuration access

        Returns:
            RmsCoordinateSystemMatch object

        Raises:
            ValueError: If config values are missing or invalid
        """
        rms_crs_config = project_session.project_fmu_directory.get_config_value(
            "rms.coordinate_system", None
        )

        if not rms_crs_config:
            raise ValueError(
                "No RMS coordinate system found in project config. "
                "Please configure rms.coordinate_system in the project config."
            )

        rms_crs = RmsCoordinateSystem.model_validate(rms_crs_config)

        smda_crs_config = project_session.project_fmu_directory.get_config_value(
            "masterdata.smda.coordinate_system", None
        )

        if not smda_crs_config:
            raise ValueError(
                "No SMDA coordinate system found in project masterdata. "
                "Please configure masterdata.smda.coordinate_system "
                "in the project config."
            )

        smda_crs = CoordinateSystem.model_validate(smda_crs_config)

        return self.match_coordinate_system(rms_crs, smda_crs)

    def match_stratigraphy(
        self,
        rms_zones: list[RmsStratigraphicZone],
        smda_units: list[StratigraphicUnit],
    ) -> list[RmsStratigraphyMatch]:
        """Match RMS zones to SMDA stratigraphic units using greedy algorithm.

        For each zone, finds the best-matching unit based on name similarity
        using token-sort ratio for flexible matching.

        Args:
            rms_zones: List of RMS stratigraphic zones to match
            smda_units: List of SMDA stratigraphic units to match against

        Returns:
            List of RmsStratigraphyMatch objects in the original zone order.
            Each zone is matched to its highest-scoring unit.
        """
        matches = []

        for zone in rms_zones:
            best_unit = None
            best_score = -1.0

            for unit in smda_units:
                score = self._calculate_name_score(zone.name, unit.identifier)

                if score > best_score:
                    best_score = score
                    best_unit = unit

            if best_unit is not None:
                confidence = self._determine_confidence(best_score)
                matches.append(
                    RmsStratigraphyMatch(
                        rms_zone=zone,
                        smda_unit=best_unit,
                        score=best_score,
                        confidence=confidence,
                    )
                )

        return matches

    def match_coordinate_system(
        self,
        rms_crs_sys: RmsCoordinateSystem,
        smda_crs_sys: CoordinateSystem,
    ) -> RmsCoordinateSystemMatch:
        """Match RMS coordinate system to SMDA coordinate system.

        Args:
            rms_crs_sys: The RMS coordinate system to be matched
            smda_crs_sys: The SMDA coordinate system to match against

        Returns:
            The CoordinateSystemMatch object with score and confidence.
        """
        score = self._calculate_name_score_strict(
            rms_crs_sys.name, smda_crs_sys.identifier
        )

        confidence = self._determine_confidence(score)
        return RmsCoordinateSystemMatch(
            rms_crs_sys=rms_crs_sys,
            smda_crs_sys=smda_crs_sys,
            score=score,
            confidence=confidence,
        )

    def _normalize_name(self, name: str) -> list[str]:
        """Normalize a name for comparison.

        Converts to lowercase, replaces underscores and dots with spaces,
        and returns list of tokens.

        Example:
            "Eiriksson Fm 2.1" -> ["eiriksson", "fm", "2", "1"]

        Args:
            name: The name to normalize

        Returns:
            List of normalized tokens
        """
        return re.sub(r"[_.]", " ", name.lower()).split()

    def _calculate_name_score_strict(self, name1: str, name2: str) -> float:
        """Calculate strict similarity score for two names.

        Uses simple ratio matching for exact word order.

        Args:
            name1: First name to compare
            name2: Second name to compare

        Returns:
            Similarity score from 0 to 100
        """
        tokens1 = self._normalize_name(name1)
        tokens2 = self._normalize_name(name2)
        return fuzz.ratio(" ".join(tokens1), " ".join(tokens2))

    def _calculate_name_score(self, name1: str, name2: str) -> float:
        """Calculate similarity score for two names.

        Uses token-sort ratio for flexible matching that allows different
        word ordering (e.g., "VIKING GP" matches "GP VIKING").

        Args:
            name1: First name to compare
            name2: Second name to compare

        Returns:
            Similarity score from 0 to 100
        """
        tokens1 = self._normalize_name(name1)
        tokens2 = self._normalize_name(name2)
        return fuzz.token_sort_ratio(" ".join(tokens1), " ".join(tokens2))

    def _determine_confidence(self, score: float) -> Literal["high", "medium", "low"]:
        """Determine confidence level based on total score.

        Args:
            score: Total similarity score (0-100)

        Returns:
            Confidence level: 'high' (>80), 'medium' (50-80), 'low' (<50)
        """
        if score > HIGH_CONFIDENCE_THRESHOLD:
            return "high"
        if score >= MEDIUM_CONFIDENCE_THRESHOLD:
            return "medium"
        return "low"
