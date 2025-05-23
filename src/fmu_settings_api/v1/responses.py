"""Contains mappings of responses that API end points return."""

from typing import Any, Final, TypeAlias

Responses: TypeAlias = dict[int | str, dict[str, Any]]

GetSessionResponses: Final[Responses] = {
    401: {
        "description": "No active or valid session was found",
        "content": {
            "application/json": {
                "example": {
                    "examples": [
                        {"detail": "No active session found"},
                        {"detail": "Invalid or expired session"},
                        {"detail": "No FMU project directory open"},
                    ],
                },
            },
        },
    },
    500: {
        "description": "Something unexpected has happened",
        "content": {
            "application/json": {
                "example": {"detail": "Session error: {string content of exception}"},
            },
        },
    },
}
