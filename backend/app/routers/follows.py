"""Follow a room by email (double opt-in), confirm it, and unsubscribe with the token from an email.

A follow starts unconfirmed and gets a confirmation email; only a confirmed follow gets digests.
The follow answer is always 201 with just what the caller sent, so it never reveals whether the
address already followed. The one token per follow is in both the confirmation and the
unsubscribe link, in the URL fragment, and reaches the server only in a JSON body.

None of these endpoints touches the room's ``last_activity_at``, writes a feed event or
notifies the live stream: following is not room activity.
"""

import logging
import re
import secrets
import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends

from app import timestamps
from app.body import JsonBody
from app.digest import EmailSender, confirmation_email, get_email_sender
from app.errors import ApiError
from app.models import RoomFollow, StoredFollow
from app.rate_limit import FOLLOW, WRITE, rate_limited
from app.store import StoreProtocol, get_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Follows"])

CONFIRM_WINDOW = timedelta(days=7)

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
    store: Annotated[StoreProtocol, Depends(get_store)],
    sender: Annotated[EmailSender, Depends(get_email_sender)],
) -> RoomFollow:
    # The room is checked before the body, so an unknown room is always a 404.
    if store.get_room(room_id) is None:
        raise ApiError(404, ROOM_NOT_FOUND_MESSAGE)
    body = raw.object()
    email = _clean_email(body.get("email"))

    with store.transaction():
        room = store.get_room(room_id)
        if room is None:  # deleted since the check above
            raise ApiError(404, ROOM_NOT_FOUND_MESSAGE)
        follow = store.get_follow_by_email(room_id, email)
        if follow is None:
            follow = StoredFollow(
                id=str(uuid.uuid4()),
                room_id=room_id,
                email=email,
                created_at=timestamps.now(),
                unsubscribe_token=secrets.token_urlsafe(32),
            )
            store.save_follow(follow)
        elif follow.confirmed_at is None:
            # A repeat restarts the 7 days to confirm, so the re-sent link works.
            follow = follow.model_copy(update={"created_at": timestamps.now()})
            store.save_follow(follow)
        else:
            follow = None  # already confirmed: nothing to send

    if follow is not None:
        _send_confirmation(sender, follow, room.name)
    return RoomFollow(room_id=room_id, email=email)


def _send_confirmation(sender: EmailSender, follow: StoredFollow, room_name: str) -> None:
    """Send after the commit; a failed send is logged (without the token) and the follow stays."""
    subject, body = confirmation_email(room_name, follow.unsubscribe_token)
    try:
        sender.send(follow.email, subject, body)
    except Exception as exc:  # noqa: BLE001 - the follow is stored; the owner can follow again
        logger.error("Follow confirmation to %s failed: %s", follow.email, type(exc).__name__)


@router.post("/follows/confirm", operation_id="confirmFollow")
def confirm_follow(raw: JsonBody, store: Annotated[StoreProtocol, Depends(get_store)]) -> dict[str, bool]:
    body = raw.object()
    token = body.get("token")
    if not isinstance(token, str):
        raise ApiError(400, TOKEN_REQUIRED_MESSAGE)

    with store.transaction():
        follow = store.get_follow_by_token(token) if token else None
        if follow is None:
            return {"confirmed": False}
        if follow.confirmed_at is not None:
            return {"confirmed": True}
        now = timestamps.now()
        if now - follow.created_at > CONFIRM_WINDOW:
            return {"confirmed": False}
        store.save_follow(follow.model_copy(update={"confirmed_at": now}))
    return {"confirmed": True}


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
