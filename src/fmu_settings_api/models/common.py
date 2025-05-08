"""Common response models from the API."""

from pydantic import BaseModel


class Message(BaseModel):
    """A generic message to return to the GUI."""

    message: str
