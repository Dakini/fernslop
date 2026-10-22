"""Authentication helpers.

There are no accounts. The ``X-Device-Id`` and ``X-Actor-Name`` headers are
self-asserted and only attribute edits to an actor; they never authorise or
deny anything, and nothing here looks anything up in the store.
"""

import unicodedata
from typing import Annotated
from urllib.parse import unquote

from fastapi import Header

from app.errors import ApiError
from app.models import ApiModel

DEVICE_ID_MAX_LENGTH = 64
ACTOR_NAME_MAX_LENGTH = 40


class Actor(ApiModel):
    """Who made an edit: a device id and a display name, both trimmed."""

    device_id: str
    name: str


def _device_id(raw: str | None) -> str:
    device_id = (raw or "").strip()
    if not device_id:
        raise ApiError(400, "X-Device-Id header is required.")
    if len(device_id) > DEVICE_ID_MAX_LENGTH:
        raise ApiError(400, f"X-Device-Id must be at most {DEVICE_ID_MAX_LENGTH} characters.")
    return device_id


def _actor_name(raw: str | None) -> str:
    if raw is None:
        raise ApiError(400, "X-Actor-Name header is required.")
    try:
        # Not unquote_plus: a literal "+" stays "+".
        name = unquote(raw, encoding="utf-8", errors="strict").strip()
    except UnicodeDecodeError:
        raise ApiError(400, "X-Actor-Name is not valid percent-encoded UTF-8.") from None
    if not name:
        raise ApiError(400, "X-Actor-Name header is required.")
    if any(unicodedata.category(char) == "Cc" for char in name):
        raise ApiError(400, "X-Actor-Name contains invalid characters.")
    if len(name) > ACTOR_NAME_MAX_LENGTH:
        raise ApiError(400, f"X-Actor-Name must be at most {ACTOR_NAME_MAX_LENGTH} characters.")
    return name


def get_actor(
    x_device_id: Annotated[str | None, Header()] = None,
    x_actor_name: Annotated[str | None, Header()] = None,
) -> Actor:
    """Dependency: ``actor: Actor = Depends(get_actor)``. Rejects with a 400 ``ApiError``."""
    device_id = _device_id(x_device_id)
    return Actor(device_id=device_id, name=_actor_name(x_actor_name))
