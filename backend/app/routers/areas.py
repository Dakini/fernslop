"""Areas: add, update and delete.

Each success writes one ``area_changed`` feed event holding the undo payload that
issue 008 applies, bumps the room's ``last_activity_at`` to the event's
``created_at``, and calls ``live.notify`` once after the store transaction has ended.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import ValidationError

from app import live, timestamps
from app.auth import Actor, get_actor
from app.body import JsonBody
from app.errors import ApiError
from app.models import AreaInput, AreaPatch, FeedEvent, RestoreAreaPayload, RoomArea
from app.store import StoreProtocol, get_store

router = APIRouter(tags=["Areas"])

MAX_LIVE_AREAS = 10

ROOM_NOT_FOUND_MESSAGE = "Room not found"
AREA_NOT_FOUND_MESSAGE = "Area not found"
TOO_MANY_AREAS_MESSAGE = f"This garden has the maximum {MAX_LIVE_AREAS} areas"
EMPTY_PATCH_MESSAGE = "Send at least one of: label, shape, x_pct, y_pct, w_pct, h_pct, colour"


def _validation_message(exc: ValidationError) -> str:
    first = exc.errors()[0]
    if first["type"] == "value_error":  # raised by the label validator with a ready-made message
        return str(first["ctx"]["error"])
    field = first["loc"][-1] if first["loc"] else "body"
    if first["type"] == "missing":
        return f"{field} is required"
    return f"{field}: {first['msg']}"


def _live_area(store: StoreProtocol, area_id: str) -> RoomArea:
    area = store.get_area(area_id)
    if area is None or area.deleted_at is not None or store.get_room(area.room_id) is None:
        raise ApiError(404, AREA_NOT_FOUND_MESSAGE)
    return area


def _record(store: StoreProtocol, actor: Actor, area: RoomArea, *, before: RoomArea | None, text: str, now) -> None:
    """Save the area and its feed event, and bump the room. Call inside a transaction."""
    room = store.get_room(area.room_id)
    store.save_area(area)
    store.save_feed_event(
        FeedEvent(
            id=str(uuid.uuid4()),
            room_id=area.room_id,
            type="area_changed",
            actor_name=actor.name,
            device_id=actor.device_id,
            room_plant_id=None,
            text=text,
            photo_url=None,
            undo_payload=RestoreAreaPayload(kind="restore_area", area=before, area_id=area.id),
            undone_at=None,
            created_at=now,
        )
    )
    room.last_activity_at = now
    store.save_room(room)


def _update_text(before: RoomArea, after: RoomArea, changed: set[str]) -> str:
    if "label" in changed:
        return f'renamed "{before.label}" to "{after.label}"'
    if changed & {"w_pct", "h_pct"}:
        return f'resized the area "{after.label}"'
    if changed & {"x_pct", "y_pct"}:
        return f'moved the area "{after.label}"'
    return f'changed the area "{after.label}"'


@router.post("/rooms/{room_id}/areas", operation_id="addArea", status_code=201)
def add_area(
    room_id: str,
    raw: JsonBody,
    store: Annotated[StoreProtocol, Depends(get_store)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> RoomArea:
    body = raw.object()
    try:
        data = AreaInput.model_validate(body)
    except ValidationError as exc:
        raise ApiError(400, _validation_message(exc)) from None

    now = timestamps.now()
    with store.transaction():
        if store.get_room(room_id) is None:
            raise ApiError(404, ROOM_NOT_FOUND_MESSAGE)
        if len(store.list_areas(room_id)) >= MAX_LIVE_AREAS:
            raise ApiError(409, TOO_MANY_AREAS_MESSAGE)

        area = RoomArea(id=str(uuid.uuid4()), room_id=room_id, deleted_at=None, **data.model_dump())
        _record(store, actor, area, before=None, text=f'added the area "{area.label}"', now=now)
    live.notify(room_id)
    return area


@router.patch("/areas/{area_id}", operation_id="updateArea")
def update_area(
    area_id: str,
    raw: JsonBody,
    store: Annotated[StoreProtocol, Depends(get_store)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> RoomArea:
    body = raw.object()
    try:
        patch = AreaPatch.model_validate(body)
    except ValidationError as exc:
        raise ApiError(400, _validation_message(exc)) from None
    sent = patch.model_dump(exclude_unset=True)
    if not sent:
        raise ApiError(400, EMPTY_PATCH_MESSAGE)

    now = timestamps.now()
    with store.transaction():
        before = _live_area(store, area_id)
        changes = {field: value for field, value in sent.items() if getattr(before, field) != value}
        if not changes:
            return before
        after = before.model_copy(update=changes)
        _record(store, actor, after, before=before, text=_update_text(before, after, set(changes)), now=now)
    live.notify(after.room_id)
    return after


@router.delete("/areas/{area_id}", operation_id="deleteArea", status_code=204)
def delete_area(
    area_id: str,
    store: Annotated[StoreProtocol, Depends(get_store)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> Response:
    now = timestamps.now()
    with store.transaction():
        before = _live_area(store, area_id)
        removed = before.model_copy(update={"deleted_at": now})
        _record(store, actor, removed, before=before, text=f'removed the area "{before.label}"', now=now)
    live.notify(removed.room_id)
    return Response(status_code=204)
