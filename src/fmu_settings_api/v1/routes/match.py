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
        replacement rules and prefix or suffix removal options before matching.

        Names are normalized before matching by lowercasing, replacing
        underscores, dots, dashes, and slashes with spaces, collapsing
        whitespace, and applying optional replacement rules. Replacement
        rules match whole normalized token sequences only, so a rule like
        `Fm -> Formation` changes `Tarbert Fm` to `Tarbert Formation`,
        while `Top -> ""` leaves `Stop Viking` unchanged.

        Callers can provide a list of individual prefixes to remove. Prefixes
        are removed only from the text before the first digit and match
        normalized tokens. Prefix removal changes only the values used for
        comparison. The original names remain in the response.

        Callers can provide a list of suffixes to remove before comparison.
        For example, providing `GL` means `30_9-B-21_C_GL` is compared as `30_9-B-21_C`.
        Suffixes match complete normalized tokens at the end of a name.
        Only the longest matching token sequence is removed, once per name.
        For example, providing `GL` and `BY1H_GL` means `30_9-B-21_C_BY1H_GL` is
        compared as `30_9-B-21_C`. The original names remain in the response.

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
        prefixes_to_remove=request.prefixes_to_remove,
        suffixes_to_remove=request.suffixes_to_remove,
    )
