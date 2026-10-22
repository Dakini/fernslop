"""Rooms: list, create, get state and delete."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from app import live, timestamps
from app.body import JsonBody
from app.errors import ApiError
from app.models import Room, RoomArea, RoomState, RoomSummary, RoomSummaryPlant
from app.store import StoreProtocol, get_store
from app.text import INVALID_CHARACTERS_MESSAGE, has_invalid_characters

router = APIRouter(tags=["Rooms"])

NAME_MAX_LENGTH = 60
DESCRIPTION_MAX_LENGTH = 200
REGION_MAX_LENGTH = 60

NAME_REQUIRED_MESSAGE = "A room needs a name"
ROOM_NOT_FOUND_MESSAGE = "Room not found"


def _optional_text(body: dict[str, Any], field: str, label: str, max_length: int) -> str:
    """A trimmed optional string field: absent means ``""``, anything but a string is a 400."""
    if field not in body:
        return ""
    value = body[field]
    if not isinstance(value, str):
        raise ApiError(400, f"{label} must be a string")
    return _checked(value.strip(), label, max_length)


def _checked(value: str, label: str, max_length: int) -> str:
    if len(value) > max_length:
        raise ApiError(400, f"{label} must be at most {max_length} characters")
    if has_invalid_characters(value):
        raise ApiError(400, INVALID_CHARACTERS_MESSAGE.format(label=label))
    return value


DEFAULT_PAGE_SIZE = 30
MAX_PAGE_SIZE = 100
LIMIT_MESSAGE = f"limit must be a whole number from 1 to {MAX_PAGE_SIZE}"
CURSOR_MESSAGE = "before is not a cursor this server gave out"


class RoomPage(BaseModel):
    """One page of the index: ``next`` is the ``before`` cursor for the page after, or null on the last."""

    rooms: list[RoomSummary]
    next: str | None


def _sort_key(room: Room) -> tuple[str, str, str]:
    """Most recent activity first; formatted stamps sort like the times, the id breaks ties."""
    stamp = timestamps.format_timestamp
    return (stamp(room.last_activity_at), stamp(room.created_at), room.id)


def _cursor(key: tuple[str, str, str]) -> str:
    return "_".join(key)


def _parse_cursor(before: str) -> tuple[str, str, str]:
    parts = before.split("_", 2)
    if len(parts) != 3 or not all(parts):
        raise ApiError(400, CURSOR_MESSAGE)
    return (parts[0], parts[1], parts[2])


def _parse_limit(limit: str | None) -> int:
    if limit is None:
        return DEFAULT_PAGE_SIZE
    if not limit.isdigit() or not 1 <= int(limit) <= MAX_PAGE_SIZE:
        raise ApiError(400, LIMIT_MESSAGE)
    return int(limit)


@router.get("/rooms", operation_id="listRooms")
def list_rooms(
    store: Annotated[StoreProtocol, Depends(get_store)],
    limit: str | None = None,
    before: str | None = None,
) -> RoomPage:
    """A fixed number of queries per page: all room rows (sorted here, the sort key lives in JSON),
    then the plants, plant categories and areas of just this page's rooms."""
    size = _parse_limit(limit)
    keyed = sorted(((_sort_key(room), room) for room in store.list_rooms()), key=lambda kr: kr[0], reverse=True)
    if before is not None:
        after = _parse_cursor(before)
        keyed = [kr for kr in keyed if kr[0] < after]
    page = keyed[:size]
    room_ids = [room.id for _, room in page]
    room_plants = store.list_room_plants_in(room_ids)
    categories = {plant.id: plant.category for plant in store.get_plants({rp.plant_id for rp in room_plants})}
    plants_by_room: dict[str, list[RoomSummaryPlant]] = {room_id: [] for room_id in room_ids}
    for rp in room_plants:
        if rp.plant_id in categories:  # reference row is gone: skip the dot rather than fail
            plants_by_room[rp.room_id].append(
                RoomSummaryPlant(x_pct=rp.x_pct, y_pct=rp.y_pct, category=categories[rp.plant_id])
            )
    areas_by_room: dict[str, list[RoomArea]] = {room_id: [] for room_id in room_ids}
    for area in store.list_areas_in(room_ids):
        areas_by_room[area.room_id].append(area)
    summaries = [
        RoomSummary(room=room, plants=plants_by_room[room.id], areas=areas_by_room[room.id]) for _, room in page
    ]
    more = len(keyed) > size
    return RoomPage(rooms=summaries, next=_cursor(page[-1][0]) if more else None)


@router.post("/rooms", operation_id="createRoom", status_code=201)
def create_room(raw: JsonBody, store: Annotated[StoreProtocol, Depends(get_store)]) -> Room:
    body = raw.object()
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ApiError(400, NAME_REQUIRED_MESSAGE)
    name = _checked(name.strip(), "Name", NAME_MAX_LENGTH)
    description = _optional_text(body, "description", "Description", DESCRIPTION_MAX_LENGTH)
    region = _optional_text(body, "region", "Region", REGION_MAX_LENGTH)

    created_at = timestamps.now()
    room = Room(
        id=str(uuid.uuid4()),
        name=name,
        description=description,
        region=region,
        created_at=created_at,
        last_activity_at=created_at,
    )
    store.save_room(room)
    return room


@router.get("/rooms/{room_id}", operation_id="getRoomState")
def get_room_state(room_id: str, store: Annotated[StoreProtocol, Depends(get_store)]) -> RoomState:
    room = store.get_room(room_id)
    if room is None:
        raise ApiError(404, ROOM_NOT_FOUND_MESSAGE)
    plants = [rp for rp in store.list_room_plants(room.id) if store.get_plant(rp.plant_id) is not None]
    return RoomState(
        room=room,
        plants=plants,
        areas=store.list_areas(room.id),
        feed=store.list_feed_events(room.id),
    )


@router.delete("/rooms/{room_id}", operation_id="deleteRoom", status_code=204)
def delete_room(room_id: str, store: Annotated[StoreProtocol, Depends(get_store)]) -> Response:
    """Soft-delete the room: it disappears from the API but nothing is removed. Needs no actor headers.

    ``app.room_purge`` removes it for good after 7 days; until then an operator can bring it back
    with ``app.room_restore``. Idempotent: a room that is already deleted (or never existed, or has
    a non-UUID id) answers 204 too, with nothing changed. Of several deletes at once exactly one
    marks the room (the store transaction is exclusive) and only that one closes the live streams.
    """
    with store.transaction():
        deleted = store.delete_room(room_id, timestamps.now())
    if deleted:
        live.close_room(room_id)  # only now that the mark has committed
    return Response(status_code=204)
