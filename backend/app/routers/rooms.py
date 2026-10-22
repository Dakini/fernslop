"""Rooms: list, create and get state."""

import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from app import timestamps
from app.errors import ApiError
from app.models import Room, RoomState, RoomSummary, RoomSummaryPlant
from app.store import StoreProtocol, get_store

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
    return value


async def _json_object(request: Request) -> dict[str, Any]:
    try:
        body = json.loads(await request.body())
    except ValueError:  # invalid JSON, or bytes that are not UTF-8
        raise ApiError(400, "Request body is not valid JSON") from None
    if not isinstance(body, dict):
        raise ApiError(400, "Request body must be a JSON object")
    return body


def _newest_first(room: Room) -> tuple:
    return (room.last_activity_at, room.created_at)


@router.get("/rooms", operation_id="listRooms")
def list_rooms(store: Annotated[StoreProtocol, Depends(get_store)]) -> list[RoomSummary]:
    summaries = []
    for room in sorted(store.list_rooms(), key=_newest_first, reverse=True):
        plants = []
        for room_plant in store.list_room_plants(room.id):
            plant = store.get_plant(room_plant.plant_id)
            if plant is None:  # reference row is gone: skip the dot rather than fail
                continue
            plants.append(RoomSummaryPlant(x_pct=room_plant.x_pct, y_pct=room_plant.y_pct, category=plant.category))
        summaries.append(RoomSummary(room=room, plants=plants, areas=store.list_areas(room.id)))
    return summaries


@router.post("/rooms", operation_id="createRoom", status_code=201)
async def create_room(request: Request, store: Annotated[StoreProtocol, Depends(get_store)]) -> Room:
    body = await _json_object(request)
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
