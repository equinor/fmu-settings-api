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

    @pytest.mark.parametrize(
        ("source", "target"),
        [
            ("VIKING GP 2 1", "viking gp 2 1"),
            ("Viking_GP_2_1", "viking-gp-2-1"),
            ("Viking/GP/2/1", "Viking.GP.2.1"),
            ("  Viking   GP  2  1  ", "viking gp 2 1"),
        ],
    )
    def test_name_normalization(
        self,
        match_service: MatchService,
        source: str,
        target: str,
    ) -> None:
        """Test supported name formatting differences are normalized."""
        results = match_service.match_names([source], [target])

        assert len(results) == 1
        assert results[0].matches[0].score == PERFECT_MATCH_SCORE
        assert results[0].matches[0].confidence == "high"

    def test_wellbore_prefixes_are_removed_before_matching(
        self, match_service: MatchService
    ) -> None:
        """Test RMS and SMDA wellbore prefixes are removed before matching."""
        results = match_service.match_names(
            ["RFT_33_5_1"],
            ["NO 33/5-1"],
            [
                MatchReplacementRule(original="RFT", replacement=""),
                MatchReplacementRule(original="NO", replacement=""),
            ],
        )

        assert len(results) == 1
        assert results[0].matches[0].score == PERFECT_MATCH_SCORE
        assert results[0].matches[0].confidence == "high"

    def test_selected_prefixes_are_removed_before_first_digit(
        self, match_service: MatchService
    ) -> None:
        """Test selected prefixes are removed from names before matching."""
        results = match_service.match_names(
            ["RFT_33_5_1"],
            ["NO RFT 33/5-1"],
            prefixes_to_remove=["NO", "RFT"],
        )

        assert results[0].source == "RFT_33_5_1"
        assert results[0].matches[0].target == "NO RFT 33/5-1"
        assert results[0].matches[0].score == PERFECT_MATCH_SCORE
        assert results[0].matches[0].confidence == "high"

    def test_custom_prefix_is_normalized_before_removal(
        self, match_service: MatchService
    ) -> None:
        """Test a caller-defined prefix uses normal name normalization."""
        results = match_service.match_names(
            ["Custom-Prefix_33_5_1"],
            ["33/5-1"],
            prefixes_to_remove=["custom_prefix"],
        )

        assert results[0].matches[0].score == PERFECT_MATCH_SCORE

    def test_multi_token_prefix_is_not_split_into_individual_prefixes(
        self, match_service: MatchService
    ) -> None:
        """Test a multi-token prefix is removed only as a complete sequence."""
        results = match_service.match_names(
            ["SEA 31/2-1"],
            ["31/2-1"],
            prefixes_to_remove=["NORTH SEA"],
        )

        assert results[0].matches[0].score < PERFECT_MATCH_SCORE

    @pytest.mark.parametrize(
        "prefixes_to_remove",
        [
            ["NORTH", "NORTH SEA"],
            ["NORTH SEA", "NORTH"],
        ],
    )
    def test_overlapping_prefixes_are_removed_in_any_request_order(
        self,
        match_service: MatchService,
        prefixes_to_remove: list[str],
    ) -> None:
        """Test overlapping selected prefixes do not depend on request order."""
        results = match_service.match_names(
            ["NORTH SEA 31/2-1"],
            ["31/2-1"],
            prefixes_to_remove=prefixes_to_remove,
        )

        assert results[0].matches[0].score == PERFECT_MATCH_SCORE

    def test_unselected_prefix_is_kept(self, match_service: MatchService) -> None:
        """Test prefix removal does not remove a prefix that was not selected."""
        results = match_service.match_names(
            ["33/5-1"],
            ["NO RFT 33/5-1"],
            prefixes_to_remove=["RFT"],
        )

        assert results[0].matches[0].score < PERFECT_MATCH_SCORE

    def test_selected_text_after_first_digit_is_kept(
        self, match_service: MatchService
    ) -> None:
        """Test selected text after the first digit is not removed."""
        results = match_service.match_names(
            ["31_2-O-13_BY1H_GL"],
            ["NO 31/2-O-13"],
            prefixes_to_remove=["NO", "GL"],
        )

        assert results[0].matches[0].score < PERFECT_MATCH_SCORE

    def test_prefix_is_not_removed_when_name_has_no_digit(
        self, match_service: MatchService
    ) -> None:
        """Test prefix removal does not change a name without a digit."""
        results = match_service.match_names(
            ["RFT Viking"],
            ["Viking"],
            prefixes_to_remove=["RFT"],
        )

        assert results[0].matches[0].score < PERFECT_MATCH_SCORE

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
