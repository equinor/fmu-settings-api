"""Tests for the MatchService."""

import pytest

from fmu_settings_api.models.match import MatchReplacementRule
from fmu_settings_api.services.match import MatchService

PERFECT_MATCH_SCORE = 100.0
LOW_CONFIDENCE_SCORE_THRESHOLD = 50


@pytest.fixture
def match_service() -> MatchService:
    """Returns a MatchService instance."""
    return MatchService()


class TestMatchNames:
    """Tests for match_names method."""

    def test_perfect_match(self, match_service: MatchService) -> None:
        """Test matching with identical names returns 100 score."""
        results = match_service.match_names(["Viking GP"], ["Viking GP"])

        assert len(results) == 1
        assert results[0].source == "Viking GP"
        assert len(results[0].matches) == 1
        assert results[0].matches[0].target == "Viking GP"
        assert results[0].matches[0].score == PERFECT_MATCH_SCORE
        assert results[0].matches[0].confidence == "high"

    def test_strict_matching_keeps_token_order(
        self, match_service: MatchService
    ) -> None:
        """Test matching does not treat reordered tokens as a perfect match."""
        results = match_service.match_names(["Viking GP"], ["GP Viking"])

        assert len(results) == 1
        assert results[0].matches[0].score < PERFECT_MATCH_SCORE

    def test_name_normalization(self, match_service: MatchService) -> None:
        """Test that names are normalized before matching."""
        results = match_service.match_names(
            ["Viking_GP-2/1"],
            ["VIKING GP 2 1"],
        )

        assert len(results) == 1
        assert results[0].matches[0].score == PERFECT_MATCH_SCORE
        assert results[0].matches[0].confidence == "high"

    def test_wellbore_name_matches_across_data_systems(
        self, match_service: MatchService
    ) -> None:
        """Test matching an RMS wellbore name against various target system formats."""
        results = match_service.match_names(
            ["30_9-B-21_C"],
            [
                "B21C",
                "NO 30/9-B-21 C",
                "30/9-B-21 C",
            ],
            [MatchReplacementRule(original="NO", replacement="")],
        )

        assert len(results) == 1
        assert results[0].source == "30_9-B-21_C"
        expected_wellbore_match_count = 3
        assert len(results[0].matches) == expected_wellbore_match_count
        assert [
            (match.target, match.score, match.confidence)
            for match in results[0].matches
        ] == [
            ("NO 30/9-B-21 C", 100.0, "high"),
            ("30/9-B-21 C", 100.0, "high"),
            ("B21C", 53.333333333333336, "medium"),
        ]

    def test_replacements_are_applied_before_matching(
        self, match_service: MatchService
    ) -> None:
        """Test that replacement rules are applied to source and target names."""
        results = match_service.match_names(
            ["Viking GP"],
            ["Viking Group"],
            [MatchReplacementRule(original="GP", replacement="Group")],
        )

        assert len(results) == 1
        assert results[0].matches[0].score == PERFECT_MATCH_SCORE
        assert results[0].matches[0].confidence == "high"

    def test_replacement_rules_are_normalized(
        self, match_service: MatchService
    ) -> None:
        """Test replacement rules match normalized token sequences."""
        results = match_service.match_names(
            ["Viking G-P"],
            ["Viking Group"],
            [MatchReplacementRule(original="g_p", replacement="GROUP")],
        )

        assert len(results) == 1
        assert results[0].matches[0].score == PERFECT_MATCH_SCORE
        assert results[0].matches[0].confidence == "high"

    def test_replacements_do_not_apply_inside_tokens(
        self, match_service: MatchService
    ) -> None:
        """Test replacement rules do not change text inside normalized tokens."""
        results = match_service.match_names(
            ["Stop Viking"],
            ["S Viking"],
            [MatchReplacementRule(original="Top", replacement="")],
        )

        assert len(results) == 1
        assert results[0].matches[0].score < PERFECT_MATCH_SCORE

    def test_replacements_can_remove_strings(self, match_service: MatchService) -> None:
        """Test that replacement rules can remove whole token sequences."""
        results = match_service.match_names(
            ["Top Viking GP"],
            ["Viking GP"],
            [MatchReplacementRule(original="Top", replacement="")],
        )

        assert len(results) == 1
        assert results[0].matches[0].score == PERFECT_MATCH_SCORE

    def test_each_source_gets_top_three_matches(
        self, match_service: MatchService
    ) -> None:
        """Test that each source gets up to three ranked target matches."""
        results = match_service.match_names(
            ["Viking GP"],
            [
                "Viking Group",
                "Viking Formation",
                "Viking",
                "Unrelated Unit",
            ],
            [
                MatchReplacementRule(original="GP", replacement="Group"),
            ],
        )

        assert len(results) == 1
        assert results[0].source == "Viking GP"
        expected_top_match_count = 3
        assert len(results[0].matches) == expected_top_match_count
        assert results[0].matches[0].target == "Viking Group"
        assert results[0].matches[0].score >= results[0].matches[1].score
        assert results[0].matches[1].score >= results[0].matches[2].score
        assert {match.target for match in results[0].matches} == {
            "Viking Group",
            "Viking Formation",
            "Viking",
        }

    def test_returns_fewer_matches_when_less_than_three_targets(
        self, match_service: MatchService
    ) -> None:
        """Test that each source gets all targets when fewer than three exist."""
        results = match_service.match_names(
            ["Viking GP", "Tarbert Fm"],
            ["Viking GP", "Tarbert Fm"],
        )

        expected_source_count = 2
        assert len(results) == expected_source_count
        assert [match.source for match in results] == ["Viking GP", "Tarbert Fm"]
        expected_match_count_per_source = 2
        assert len(results[0].matches) == expected_match_count_per_source
        assert len(results[1].matches) == expected_match_count_per_source

    def test_multiple_sources_get_grouped_matches(
        self, match_service: MatchService
    ) -> None:
        """Test each source result contains only its own target candidates."""
        results = match_service.match_names(
            ["Viking GP", "Tarbert Fm"],
            ["Viking Group", "Tarbert Formation", "Unrelated Unit"],
            [
                MatchReplacementRule(original="GP", replacement="Group"),
                MatchReplacementRule(original="Fm", replacement="Formation"),
            ],
        )

        expected_source_count = 2
        assert len(results) == expected_source_count
        assert results[0].source == "Viking GP"
        assert results[0].matches[0].target == "Viking Group"
        assert results[1].source == "Tarbert Fm"
        assert results[1].matches[0].target == "Tarbert Formation"

    def test_empty_sources(self, match_service: MatchService) -> None:
        """Test matching with empty sources returns an empty list."""
        results = match_service.match_names([], ["Viking GP"])

        assert results == []

    def test_empty_targets(self, match_service: MatchService) -> None:
        """Test matching with empty targets returns sources with empty matches."""
        results = match_service.match_names(["Viking GP"], [])

        assert len(results) == 1
        assert results[0].source == "Viking GP"
        assert results[0].matches == []

    def test_multiple_sources_preserved_order(
        self, match_service: MatchService
    ) -> None:
        """Test that matching preserves the original source order."""
        results = match_service.match_names(
            ["Zone A", "Zone B", "Zone C"],
            ["Unit A"],
        )

        expected_source_count = 3
        assert len(results) == expected_source_count
        assert results[0].source == "Zone A"
        assert results[1].source == "Zone B"
        assert results[2].source == "Zone C"

    def test_low_confidence_match(self, match_service: MatchService) -> None:
        """Test matching with very different names returns low confidence."""
        results = match_service.match_names(["ED50"], ["WGS84 UTM Zone 32"])

        assert len(results) == 1
        assert results[0].matches[0].score < LOW_CONFIDENCE_SCORE_THRESHOLD
        assert results[0].matches[0].confidence == "low"
