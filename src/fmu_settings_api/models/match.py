"""Models for matching names."""

import re
from typing import Literal

from pydantic import Field, field_validator

from fmu_settings_api.models.common import BaseResponseModel


class MatchReplacementRule(BaseResponseModel):
    """A normalized token sequence replacement to apply before matching."""

    original: str
    """The normalized token sequence to replace."""

    replacement: str
    """The replacement token sequence."""

    @field_validator("original")
    @classmethod
    def original_must_not_normalize_to_empty(cls, value: str) -> str:
        """Validate that original contains something replaceable."""
        if not re.sub(r"[_.\-/]", " ", value).strip():
            msg = (
                "Original must include text after normalization. Empty values and "
                'separators such as "_", ".", "-", and "/" cannot be replaced. '
                "Those separators are normalized automatically. Replacement rules "
                'are only needed for text values, for example "Fm" -> "Formation".'
            )
            raise ValueError(msg)
        return value


class MatchRequest(BaseResponseModel):
    """A request to match source names against target names."""

    sources: list[str]
    """Names to match from."""

    targets: list[str]
    """Names to match against."""

    replacements: list[MatchReplacementRule] = Field(default_factory=list)
    """Optional normalized token sequence replacements to apply before matching."""


class MatchCandidate(BaseResponseModel):
    """A target candidate for a source name."""

    target: str
    """The candidate target name."""

    score: float = Field(ge=0, le=100)
    """Similarity score for the normalized source and target names (0-100)."""

    confidence: Literal["high", "medium", "low"]
    """Confidence level based on score.

    'high' (>80), 'medium' (50-80), 'low' (<50).
    """


class MatchResult(BaseResponseModel):
    """The target candidates for a source name."""

    source: str
    """The source name."""

    matches: list[MatchCandidate]
    """The best target candidates for the source name."""
