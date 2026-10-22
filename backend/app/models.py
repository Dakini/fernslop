"""Shared API models."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, PlainSerializer

from app.timestamps import format_timestamp


class ApiModel(BaseModel):
    """Base class for every request and response model."""


class Error(BaseModel):
    """The body of every error response."""

    message: str


Timestamp = Annotated[
    datetime,
    PlainSerializer(format_timestamp, return_type=str, when_used="json"),
]
