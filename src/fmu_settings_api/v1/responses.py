"""Contains mappings of responses that API end points return."""

from copy import deepcopy
from textwrap import dedent
from typing import Any, Final, TypeAlias

Responses: TypeAlias = dict[int | str, dict[str, Any]]


def add_response_example(
    responses: Responses, http_code: int, example: dict[str, str]
) -> Responses:
    """Adds an example to an existing responses list."""
    new_responses = deepcopy(responses)
    new_responses[http_code]["content"]["application/json"]["example"][
        "examples"
    ].append(example)
    return new_responses


def inline_add_response(
    http_code: int, description: str, examples: list[dict[str, str]]
) -> Responses:
    """Inline-adds a response with examples."""
    return {
        http_code: {
            "description": description,
            "content": {
                "application/json": {
                    "example": {"examples": examples},
                },
            },
        },
    }


CreateSessionResponses: Final[Responses] = {
    **inline_add_response(
        401,
        dedent(
            """
            Occurs when no token or an invalid token is or is not provided
            with the x-fmu-settings-api header.
            """
        ),
        [
            {"detail": "Not authorized"},
        ],
    ),
    **inline_add_response(
        403,
        dedent(
            """
            Will occur if the operating system claims the user does not have
            permission to create $HOME/.fmu. If returned something very wrong
            is happening.
            """
        ),
        [{"detail": "Permission denied creating user .fmu"}],
    ),
    **inline_add_response(
        409,
        dedent(
            """
            Occurs in two cases:

            - When attempting to create a session when one already exists
            - When trying to create a user .fmu directory, but it already
            exists. Typically means that .fmu exists as a file.
            """
        ),
        [
            {"detail": "A session already exists"},
            {
                "detail": (
                    "User .fmu already exists but is invalid (i.e. is not a directory)"
                ),
            },
        ],
    ),
    **inline_add_response(
        500,
        "Something unexpected has happened",
        [{"detail": "{string content of exception}"}],
    ),
}

GetSessionResponses: Final[Responses] = {
    **inline_add_response(
        401,
        "No active or valid session was found",
        [
            {"detail": "No active session found"},
            {"detail": "Invalid or expired session"},
            {"detail": "No FMU project directory open"},
        ],
    ),
    **inline_add_response(
        500,
        "Something unexpected has happened",
        [
            {"detail": "Session error: {string content of exception}"},
            {"detail": "{string content of exception}"},
        ],
    ),
}
