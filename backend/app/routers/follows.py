"""Follow a room by email, and unsubscribe with the token from a digest email.

Neither endpoint touches the room's ``last_activity_at``, writes a feed event or
notifies the live stream: following is not room activity.
"""

import re
import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app import timestamps
from app.body import JsonBody
from app.errors import ApiError
from app.models import RoomFollow, StoredFollow
from app.rate_limit import FOLLOW, WRITE, rate_limited
from app.store import StoreProtocol, get_store

router = APIRouter(tags=["Follows"])

EMAIL_MAX_LENGTH = 254
BAD_EMAIL_MESSAGE = "That email doesn't look right"
ROOM_NOT_FOUND_MESSAGE = "Room not found"
TOKEN_REQUIRED_MESSAGE = "token must be a string"

# One "@", no spaces, and a dot in the domain with something on each side of every dot.
_EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+")


def _clean_email(value: object) -> str:
    if not isinstance(value, str):
        raise ApiError(400, BAD_EMAIL_MESSAGE)
    email = value.strip().lower()
    if len(email) > EMAIL_MAX_LENGTH or not _EMAIL_PATTERN.fullmatch(email):
        raise ApiError(400, BAD_EMAIL_MESSAGE)
    return email


@router.post("/rooms/{room_id}/follows", operation_id="followRoom", status_code=201, dependencies=[rate_limited(FOLLOW)])
def follow_room(
    room_id: str,
    raw: JsonBody,
    response: Response,
    store: Annotated[StoreProtocol, Depends(get_store)],
) -> RoomFollow:
    # The room is checked before the body, so an unknown room is always a 404.
    if store.get_room(room_id) is None:
        raise ApiError(404, ROOM_NOT_FOUND_MESSAGE)
    body = raw.object()
    email = _clean_email(body.get("email"))

    with store.transaction():
        if store.get_room(room_id) is None:  # deleted since the check above
            raise ApiError(404, ROOM_NOT_FOUND_MESSAGE)
        existing = store.get_follow_by_email(room_id, email)
        if existing is not None:
            response.status_code = 200
            return existing.to_public()
        follow = StoredFollow(
            id=str(uuid.uuid4()),
            room_id=room_id,
            email=email,
            created_at=timestamps.now(),
            unsubscribe_token=secrets.token_urlsafe(32),
        )
        store.save_follow(follow)
    return follow.to_public()


@router.post("/follows/unsubscribe", operation_id="unfollow", dependencies=[rate_limited(WRITE)])
def unfollow(raw: JsonBody, store: Annotated[StoreProtocol, Depends(get_store)]) -> dict[str, bool]:
    body = raw.object()
    token = body.get("token")
    if not isinstance(token, str):
        raise ApiError(400, TOKEN_REQUIRED_MESSAGE)

    with store.transaction():
        follow = store.get_follow_by_token(token) if token else None
        removed = store.delete_follow(follow.id) if follow is not None else False
    return {"unsubscribed": removed}
