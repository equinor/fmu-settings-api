"""Contains mappings of responses that API end points return."""

from typing import Any, Final, TypeAlias

Responses: TypeAlias = dict[int | str, dict[str, Any]]

CreateSessionResponses: Final[Responses] = {
    401: {
        "description": (
            "Occurs when no token or an invalid token is or is not provided "
            "with the x-fmu-settings-api header."
        ),
        "content": {
            "application/json": {
                "example": {"detail": "Not authorized"},
            },
        },
    },
    403: {
        "description": (
            "Will occur if the operating system claims the user does not have "
            "permission to create $HOME/.fmu. If returned something very wrong "
            "is happening."
        ),
        "content": {
            "application/json": {
                "example": {"detail": "Permission denied creating user .fmu"},
            },
        },
    },
    409: {
        "description": (
            "Occurs in two cases:\n"
            "- When attempting to create a session when one already exists\n"
            "- When trying to create a user .fmu directory, but it already "
            "exists. Typically means that .fmu exists as a file."
        ),
        "content": {
            "application/json": {
                "example": {
                    "examples": [
                        {"detail": "A session already exists"},
                        {
                            "detail": (
                                "User .fmu already exists but is invalid (i.e. "
                                "is not a directory)"
                            ),
                        },
                    ],
                },
            },
        },
    },
    500: {
        "description": "Something unexpected has happened",
        "content": {
            "application/json": {
                "example": {"detail": "{string content of exception}"},
            },
        },
    },
}

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
