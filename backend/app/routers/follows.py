"""Follow a room by email, and unsubscribe with the token from a digest email.

Neither endpoint touches the room's ``last_activity_at``, writes a feed event or
notifies the live stream: following is not room activity.
"""

import json
import re
import secrets
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from app import timestamps
from app.errors import ApiError
from app.models import RoomFollow, StoredFollow
from app.store import StoreProtocol, get_store

router = APIRouter(tags=["Follows"])

EMAIL_MAX_LENGTH = 254
BAD_EMAIL_MESSAGE = "That email doesn't look right"
ROOM_NOT_FOUND_MESSAGE = "Room not found"
TOKEN_REQUIRED_MESSAGE = "token must be a string"

# One "@", no spaces, and a dot in the domain with something on each side of every dot.
_EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+")


async def _json_object(request: Request) -> dict[str, Any]:
    try:
        body = json.loads(await request.body())
    except ValueError:  # invalid JSON, or bytes that are not UTF-8
        raise ApiError(400, "Request body is not valid JSON") from None
    if not isinstance(body, dict):
        raise ApiError(400, "Request body must be a JSON object")
    return body


def _clean_email(value: object) -> str:
    if not isinstance(value, str):
        raise ApiError(400, BAD_EMAIL_MESSAGE)
    email = value.strip().lower()
    if len(email) > EMAIL_MAX_LENGTH or not _EMAIL_PATTERN.fullmatch(email):
        raise ApiError(400, BAD_EMAIL_MESSAGE)
    return email


@router.post("/rooms/{room_id}/follows", operation_id="followRoom", status_code=201)
async def follow_room(
    room_id: str,
    request: Request,
    response: Response,
    store: Annotated[StoreProtocol, Depends(get_store)],
) -> RoomFollow:
    # The room is checked before the body, so an unknown room is always a 404.
    if store.get_room(room_id) is None:
        raise ApiError(404, ROOM_NOT_FOUND_MESSAGE)
    body = await _json_object(request)
    email = _clean_email(body.get("email"))

    with store.transaction():
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


@router.post("/follows/unsubscribe", operation_id="unfollow")
async def unfollow(request: Request, store: Annotated[StoreProtocol, Depends(get_store)]) -> dict[str, bool]:
    body = await _json_object(request)
    token = body.get("token")
    if not isinstance(token, str):
        raise ApiError(400, TOKEN_REQUIRED_MESSAGE)

    with store.transaction():
        follow = store.get_follow_by_token(token) if token else None
        removed = store.delete_follow(follow.id) if follow is not None else False
    return {"unsubscribed": removed}
