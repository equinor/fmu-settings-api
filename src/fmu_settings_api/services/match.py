"""Service for matching names."""

import re
from typing import Literal

from rapidfuzz import fuzz, process

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
        *,
        prefixes_to_remove: list[str] | None = None,
    ) -> list[MatchResult]:
        """Match source names to target names using strict name similarity.

        For each source name, finds the three highest-scoring target names
        using strict ratio matching after normalization.

        Args:
            sources: Names to match from.
            targets: Names to match against.
            replacements: Optional string replacements to apply before matching.
            prefixes_to_remove: Optional prefixes to remove from the text before
                the first digit.

        Returns:
            Match results in the original source order. Each source result
            includes up to three targets, ordered from highest to lowest score.
        """
        matches = []
        prepared_replacements: list[tuple[re.Pattern[str], str]] = []
        for replacement in replacements or []:
            original = self._normalize_text(replacement.original)
            pattern = re.compile(rf"(?<!\S){re.escape(original)}(?!\S)")
            prepared_replacements.append(
                (pattern, self._normalize_text(replacement.replacement))
            )

        prefix_sequences_to_remove: list[tuple[str, ...]] = []
        for prefix in prefixes_to_remove or []:
            normalized_prefix = self._normalize_text(prefix)
            if normalized_prefix:
                prefix_sequences_to_remove.append(tuple(normalized_prefix.split()))

        normalized_targets = [
            self._normalize_name(
                target,
                prepared_replacements,
                prefix_sequences_to_remove,
            )
            for target in targets
        ]

        for source in sources:
            normalized_source = self._normalize_name(
                source,
                prepared_replacements,
                prefix_sequences_to_remove,
            )
            target_scores = [
                (targets[target_index], score)
                for _, score, target_index in process.extract(
                    normalized_source,
                    normalized_targets,
                    scorer=fuzz.ratio,
                    limit=TOP_MATCHES_PER_SOURCE,
                )
            ]

            matches.append(
                MatchResult(
                    source=source,
                    matches=[
                        MatchCandidate(
                            target=target,
                            score=score,
                            confidence=self._determine_confidence(score),
                        )
                        for target, score in target_scores
                    ],
                )
            )

        return matches

    def _normalize_name(
        self,
        name: str,
        prepared_replacements: list[tuple[re.Pattern[str], str]],
        prefix_sequences_to_remove: list[tuple[str, ...]],
    ) -> str:
        """Normalize a name for comparison.

        Converts to lowercase, replaces underscores, dots, dashes, and slashes
        with spaces, collapses whitespace, removes requested prefixes, and
        applies replacement rules to whole normalized token sequences only.

        Example:
            With replacement {"original": "fm", "replacement": "formation"}:
            "Eiriksson_Fm-2/1.1" -> "eiriksson formation 2 1 1"
            With replacement {"original": "top", "replacement": ""}:
            "Stop Viking" -> "stop viking", because "top" is not a whole token.

        Args:
            name: The name to normalize.
            prepared_replacements: Normalized replacement patterns and values.
            prefix_sequences_to_remove: Normalized prefix sequences to remove
                from the text before the first digit.

        Returns:
            Normalized name.
        """
        normalized_name = self._normalize_text(name)
        normalized_name = self._remove_prefix_sequences(
            normalized_name,
            prefix_sequences_to_remove,
        )

        for pattern, replacement_value in prepared_replacements:
            normalized_name = pattern.sub(replacement_value, normalized_name)
            normalized_name = " ".join(normalized_name.split())

        return normalized_name

    @staticmethod
    def _remove_prefix_sequences(
        normalized_name: str,
        prefix_sequences_to_remove: list[tuple[str, ...]],
    ) -> str:
        """Remove complete selected prefix sequences before the first digit."""
        first_digit = re.search(r"\d", normalized_name)
        if not first_digit or not prefix_sequences_to_remove:
            return normalized_name

        first_digit_index = first_digit.start()
        prefix_tokens = normalized_name[:first_digit_index].split()
        token_indexes_to_remove: set[int] = set()

        for prefix_sequence in prefix_sequences_to_remove:
            sequence_length = len(prefix_sequence)
            for start_index in range(len(prefix_tokens) - sequence_length + 1):
                end_index = start_index + sequence_length
                if tuple(prefix_tokens[start_index:end_index]) == prefix_sequence:
                    token_indexes_to_remove.update(range(start_index, end_index))

        kept_prefix = " ".join(
            token
            for index, token in enumerate(prefix_tokens)
            if index not in token_indexes_to_remove
        )
        return f"{kept_prefix} {normalized_name[first_digit_index:]}".strip()

    @staticmethod
    def _normalize_text(value: str) -> str:
        """Normalize case, supported separators, and whitespace."""
        return " ".join(re.sub(r"[_.\-/]", " ", value.lower()).split())

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
