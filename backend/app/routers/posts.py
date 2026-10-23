"""Feed posts: text and/or a previously uploaded photo.

A success saves the ``post`` event and bumps the room's ``last_activity_at`` in
one store transaction, then calls ``live.notify`` once after it has ended.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app import live, timestamps
from app.auth import Actor, get_actor
from app.body import JsonBody
from app.errors import ApiError
from app.models import FeedEvent
from app.rate_limit import WRITE, rate_limited
from app.store import StoreProtocol, get_store
from app.text import (
    INVALID_CHARACTERS_MESSAGE,
    has_invalid_characters,
    normalise_newlines,
)

router = APIRouter(tags=["Feed"])

TEXT_MAX_LENGTH = 1000

ROOM_NOT_FOUND_MESSAGE = "Room not found"
EMPTY_POST_MESSAGE = "Write something or add a photo"
TEXT_TOO_LONG_MESSAGE = f"Text must be at most {TEXT_MAX_LENGTH} characters"
BAD_TEXT_MESSAGE = "text must be a string"
BAD_CHARACTERS_MESSAGE = INVALID_CHARACTERS_MESSAGE.format(label="Text")
BAD_PHOTO_MESSAGE = "That photo didn't upload — try again"
PHOTO_IN_USE_MESSAGE = "That photo is already in a post"


@router.post("/rooms/{room_id}/posts", operation_id="postUpdate", status_code=201, dependencies=[rate_limited(WRITE)])
def post_update(
    room_id: str,
    raw: JsonBody,
    store: Annotated[StoreProtocol, Depends(get_store)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> FeedEvent:
    body = raw.object()

    # A missing text counts as empty; an explicit non-string (including null) is an error.
    text = body.get("text", "")
    if not isinstance(text, str):
        raise ApiError(400, BAD_TEXT_MESSAGE)
    text = normalise_newlines(text).strip()
    if len(text) > TEXT_MAX_LENGTH:
        raise ApiError(400, TEXT_TOO_LONG_MESSAGE)
    if has_invalid_characters(text, multiline=True):
        raise ApiError(400, BAD_CHARACTERS_MESSAGE)

    # A missing photo_id counts as empty. Extra fields (such as photo_url) are ignored.
    photo_id = body.get("photo_id")
    if photo_id is not None and not isinstance(photo_id, str):
        raise ApiError(400, BAD_PHOTO_MESSAGE)

    now = timestamps.now()
    with store.transaction():
        room = store.get_room(room_id)
        if room is None:
            raise ApiError(404, ROOM_NOT_FOUND_MESSAGE)

        photo_url = None
        if photo_id is not None:
            photo = store.get_photo(photo_id)
            if photo is None:
                raise ApiError(400, BAD_PHOTO_MESSAGE)
            # Any post shows it: other rooms, undone posts and soft-deleted rooms not yet purged.
            if store.photo_url_in_feed(photo.url):
                raise ApiError(400, PHOTO_IN_USE_MESSAGE)
            photo_url = photo.url
        elif not text:
            raise ApiError(400, EMPTY_POST_MESSAGE)

        event = FeedEvent(
            id=str(uuid.uuid4()),
            room_id=room_id,
            type="post",
            actor_name=actor.name,
            device_id=actor.device_id,
            room_plant_id=None,
            text=text,
            photo_url=photo_url,
            undo_payload=None,
            undone_at=None,
            created_at=now,
        )
        store.save_feed_event(event)
        room.last_activity_at = now
        store.save_room(room)
    live.notify(room_id)
    return event
