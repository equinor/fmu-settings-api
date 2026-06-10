"""Routes for matching."""

from textwrap import dedent
from typing import Final

from fastapi import APIRouter

from fmu_settings_api.deps.match import MatchServiceDep
from fmu_settings_api.models.match import MatchRequest, MatchResult
from fmu_settings_api.v1.responses import Responses, inline_add_response

MatchResponses: Final[Responses] = {
    **inline_add_response(
        422,
        "The request body is missing required match input or contains invalid data.",
        [
            {"detail": "Field required"},
            {"detail": "Input should be a valid list"},
        ],
    ),
}

router = APIRouter(prefix="/match", tags=["match"])


@router.post(
    "",
    response_model=list[MatchResult],
    summary="Match source names to target names",
    description=dedent(
        """
        Match source names to target names using strict name similarity.

        The endpoint is a pure matching utility. Callers provide both the
        source names and target names, and can optionally provide string
        replacement rules to apply before matching.

        Names are normalized before matching by lowercasing, replacing
        underscores, dots, dashes, and slashes with spaces, collapsing
        whitespace, and applying optional replacement rules. Replacement
        rules match whole normalized token sequences only, so a rule like
        `Fm -> Formation` changes `Tarbert Fm` to `Tarbert Formation`,
        while `Top -> ""` leaves `Stop Viking` unchanged.

        The response contains one result per source. Each result contains up
        to three target matches, ordered from highest to lowest score.

        Confidence levels:
        - 'high': score > 80
        - 'medium': score 50-80
        - 'low': score < 50
        """
    ),
    responses=MatchResponses,
)
async def post_match(
    request: MatchRequest,
    match_service: MatchServiceDep,
) -> list[MatchResult]:
    """Match source names to target names."""
    return match_service.match_names(
        request.sources,
        request.targets,
        request.replacements,
    )
