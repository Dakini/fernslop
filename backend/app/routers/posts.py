"""Feed posts: text and/or a previously uploaded photo.

A success saves the ``post`` event and bumps the room's ``last_activity_at`` in
one store transaction, then calls ``live.notify`` once after it has ended.
"""

import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from app import live, timestamps
from app.auth import Actor, get_actor
from app.errors import ApiError
from app.models import FeedEvent
from app.store import StoreProtocol, get_store

router = APIRouter(tags=["Feed"])

TEXT_MAX_LENGTH = 1000

ROOM_NOT_FOUND_MESSAGE = "Room not found"
EMPTY_POST_MESSAGE = "Write something or add a photo"
TEXT_TOO_LONG_MESSAGE = f"Text must be at most {TEXT_MAX_LENGTH} characters"
BAD_TEXT_MESSAGE = "text must be a string"
BAD_PHOTO_MESSAGE = "That photo didn't upload — try again"


async def _json_object(request: Request) -> dict[str, Any]:
    try:
        body = json.loads(await request.body())
    except ValueError:  # invalid JSON, or bytes that are not UTF-8
        raise ApiError(400, "Request body is not valid JSON") from None
    if not isinstance(body, dict):
        raise ApiError(400, "Request body must be a JSON object")
    return body


@router.post("/rooms/{room_id}/posts", operation_id="postUpdate", status_code=201)
async def post_update(
    room_id: str,
    request: Request,
    store: Annotated[StoreProtocol, Depends(get_store)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> FeedEvent:
    body = await _json_object(request)

    # A missing text counts as empty; an explicit non-string (including null) is an error.
    text = body.get("text", "")
    if not isinstance(text, str):
        raise ApiError(400, BAD_TEXT_MESSAGE)
    text = text.strip()
    if len(text) > TEXT_MAX_LENGTH:
        raise ApiError(400, TEXT_TOO_LONG_MESSAGE)

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
