"""Service for matching names."""

import re
from typing import Literal

from rapidfuzz import fuzz

from fmu_settings_api.models.match import (
    MatchCandidate,
    MatchReplacementRule,
    MatchResult,
)

HIGH_CONFIDENCE_THRESHOLD = 80
MEDIUM_CONFIDENCE_THRESHOLD = 50
TOP_MATCHES_PER_SOURCE = 3


class MatchService:
    """Service for matching names."""

    def match_names(
        self,
        sources: list[str],
        targets: list[str],
        replacements: list[MatchReplacementRule] | None = None,
    ) -> list[MatchResult]:
        """Match source names to target names using strict name similarity.

        For each source name, finds the three highest-scoring target names
        using strict ratio matching after normalization.

        Args:
            sources: Names to match from.
            targets: Names to match against.
            replacements: Optional string replacements to apply before matching.

        Returns:
            Match results in the original source order. Each source result
            includes up to three targets, ordered from highest to lowest score.
        """
        matches = []

        for source in sources:
            target_scores = sorted(
                (
                    (
                        target,
                        self._calculate_name_score(source, target, replacements),
                    )
                    for target in targets
                ),
                key=lambda target_score: target_score[1],
                reverse=True,
            )

            matches.append(
                MatchResult(
                    source=source,
                    matches=[
                        MatchCandidate(
                            target=target,
                            score=score,
                            confidence=self._determine_confidence(score),
                        )
                        for target, score in target_scores[:TOP_MATCHES_PER_SOURCE]
                    ],
                )
            )

        return matches

    def _calculate_name_score(
        self,
        name1: str,
        name2: str,
        replacements: list[MatchReplacementRule] | None = None,
    ) -> float:
        """Calculate strict similarity score for two names.

        Args:
            name1: First name to compare.
            name2: Second name to compare.
            replacements: Optional string replacements to apply.

        Returns:
            Similarity score from 0 to 100.
        """
        return fuzz.ratio(
            self._normalize_name(name1, replacements),
            self._normalize_name(name2, replacements),
        )

    def _normalize_name(
        self,
        name: str,
        replacements: list[MatchReplacementRule] | None = None,
    ) -> str:
        """Normalize a name for comparison.

        Converts to lowercase, replaces underscores, dots, dashes, and slashes
        with spaces, collapses whitespace, and applies replacement rules to
        whole normalized token sequences only.

        Example:
            With replacement {"original": "fm", "replacement": "formation"}:
            "Eiriksson_Fm-2/1.1" -> "eiriksson formation 2 1 1"
            With replacement {"original": "top", "replacement": ""}:
            "Stop Viking" -> "stop viking", because "top" is not a whole token.

        Args:
            name: The name to normalize.
            replacements: Optional string replacements to apply.

        Returns:
            Normalized name.
        """
        normalized_name = " ".join(re.sub(r"[_.\-/]", " ", name.lower()).split())

        for replacement in replacements or []:
            original = " ".join(
                re.sub(r"[_.\-/]", " ", replacement.original.lower()).split()
            )
            replacement_value = " ".join(
                re.sub(r"[_.\-/]", " ", replacement.replacement.lower()).split()
            )
            pattern = rf"(?<!\S){re.escape(original)}(?!\S)"

            normalized_name = re.sub(pattern, replacement_value, normalized_name)
            normalized_name = " ".join(normalized_name.split())

        return normalized_name

    def _determine_confidence(self, score: float) -> Literal["high", "medium", "low"]:
        """Determine confidence level based on total score.

        Args:
            score: Total similarity score (0-100).

        Returns:
            Confidence level: 'high' (>80), 'medium' (50-80), 'low' (<50).
        """
        if score > HIGH_CONFIDENCE_THRESHOLD:
            return "high"
        if score >= MEDIUM_CONFIDENCE_THRESHOLD:
            return "medium"
        return "low"
