"""Room plants: add, move, remove and mark care.

Each success writes one feed event holding the undo payload that issue 008
applies, bumps the room's ``last_activity_at`` to the event's ``created_at``,
and calls ``live.notify`` once after the store transaction has ended.
"""

import math
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response

from app import live, timestamps
from app.auth import Actor, get_actor
from app.body import JsonBody
from app.errors import ApiError
from app.models import (
    DeletePlantPayload,
    FeedEvent,
    FeedEventType,
    RestorePlantPayload,
    RoomPlant,
    UndoPayload,
)
from app.rate_limit import WRITE, rate_limited
from app.store import StoreProtocol, get_store

router = APIRouter(tags=["Room plants"])

MAX_LIVE_PLANTS = 50

ROOM_NOT_FOUND_MESSAGE = "Room not found"
PLANT_NOT_FOUND_MESSAGE = "Plant not found"
PLANT_GONE_MESSAGE = "Plant is no longer in this garden"
GARDEN_FULL_MESSAGE = f"This garden is full ({MAX_LIVE_PLANTS} plants max)"

# care name -> (RoomPlant timestamp field, Plant interval field, feed text verb)
CARE_TYPES = {
    "water": ("last_watered_at", "water_every_days", "watered"),
    "feed": ("last_fed_at", "feed_every_days", "fed"),
    "prune": ("last_pruned_at", "prune_every_days", "pruned"),
    "harvest": ("last_harvested_at", "harvest_every_days", "harvested"),
}


def _coordinate(body: dict[str, Any], field: str) -> float:
    """A number from the body clamped to 0-100. Missing, null, boolean or non-number is a 400."""
    value = body.get(field)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ApiError(400, f"{field} must be a number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ApiError(400, f"{field} must be a number")
    return float(min(max(value, 0), 100))


def _live_room_plant(store: StoreProtocol, room_plant_id: str) -> RoomPlant:
    room_plant = store.get_room_plant(room_plant_id)
    if room_plant is None or room_plant.deleted_at is not None or store.get_room(room_plant.room_id) is None:
        raise ApiError(404, PLANT_GONE_MESSAGE)
    return room_plant


def _display_name(store: StoreProtocol, room_plant: RoomPlant) -> str:
    if room_plant.nickname:
        return room_plant.nickname
    plant = store.get_plant(room_plant.plant_id)
    return plant.common_name if plant else "plant"


def _record(
    store: StoreProtocol,
    actor: Actor,
    room_plant: RoomPlant,
    *,
    type_: FeedEventType,
    text: str,
    undo_payload: UndoPayload,
    now,
) -> None:
    """Save the changed plant and its feed event, and bump the room. Call inside a transaction."""
    room = store.get_room(room_plant.room_id)
    store.save_room_plant(room_plant)
    store.save_feed_event(
        FeedEvent(
            id=str(uuid.uuid4()),
            room_id=room_plant.room_id,
            type=type_,
            actor_name=actor.name,
            device_id=actor.device_id,
            room_plant_id=room_plant.id,
            text=text,
            photo_url=None,
            undo_payload=undo_payload,
            undone_at=None,
            created_at=now,
        )
    )
    room.last_activity_at = now
    store.save_room(room)


@router.post("/rooms/{room_id}/plants", operation_id="addPlant", status_code=201, dependencies=[rate_limited(WRITE)])
def add_plant(
    room_id: str,
    raw: JsonBody,
    store: Annotated[StoreProtocol, Depends(get_store)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> RoomPlant:
    body = raw.object()
    plant_id = body.get("plant_id")
    if not isinstance(plant_id, str):
        raise ApiError(400, "plant_id must be a string")

    now = timestamps.now()
    with store.transaction():
        if store.get_room(room_id) is None:
            raise ApiError(404, ROOM_NOT_FOUND_MESSAGE)
        plant = store.get_plant(plant_id)
        if plant is None:
            raise ApiError(404, PLANT_NOT_FOUND_MESSAGE)
        if len(store.list_room_plants(room_id)) >= MAX_LIVE_PLANTS:
            raise ApiError(409, GARDEN_FULL_MESSAGE)

        room_plant = RoomPlant(
            id=str(uuid.uuid4()),
            room_id=room_id,
            plant_id=plant.id,
            nickname=None,
            x_pct=50,
            y_pct=50,
            last_watered_at=None,
            last_fed_at=None,
            last_pruned_at=None,
            last_harvested_at=None,
            added_by_name=actor.name,
            created_at=now,
            deleted_at=None,
        )
        _record(
            store,
            actor,
            room_plant,
            type_="plant_added",
            text=f"added a {plant.common_name}",
            undo_payload=DeletePlantPayload(kind="delete_plant", room_plant_id=room_plant.id),
            now=now,
        )
    live.notify(room_id)
    return room_plant


@router.patch("/room-plants/{room_plant_id}", operation_id="movePlant", dependencies=[rate_limited(WRITE)])
def move_plant(
    room_plant_id: str,
    raw: JsonBody,
    store: Annotated[StoreProtocol, Depends(get_store)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> RoomPlant:
    body = raw.object()
    x_pct = _coordinate(body, "x_pct")
    y_pct = _coordinate(body, "y_pct")

    now = timestamps.now()
    with store.transaction():
        before = _live_room_plant(store, room_plant_id)
        moved = before.model_copy(update={"x_pct": x_pct, "y_pct": y_pct})
        _record(
            store,
            actor,
            moved,
            type_="plant_moved",
            text=f"moved the {_display_name(store, before)}",
            undo_payload=RestorePlantPayload(kind="restore_plant", room_plant=before),
            now=now,
        )
    live.notify(moved.room_id)
    return moved


@router.delete("/room-plants/{room_plant_id}", operation_id="removePlant", status_code=204, dependencies=[rate_limited(WRITE)])
def remove_plant(
    room_plant_id: str,
    store: Annotated[StoreProtocol, Depends(get_store)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> Response:
    now = timestamps.now()
    with store.transaction():
        before = _live_room_plant(store, room_plant_id)
        removed = before.model_copy(update={"deleted_at": now})
        _record(
            store,
            actor,
            removed,
            type_="plant_removed",
            text=f"removed the {_display_name(store, before)}",
            undo_payload=RestorePlantPayload(kind="restore_plant", room_plant=before),
            now=now,
        )
    live.notify(removed.room_id)
    return Response(status_code=204)


@router.post("/room-plants/{room_plant_id}/care", operation_id="markCare", dependencies=[rate_limited(WRITE)])
def mark_care(
    room_plant_id: str,
    raw: JsonBody,
    store: Annotated[StoreProtocol, Depends(get_store)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> RoomPlant:
    body = raw.object()
    care = body.get("care")
    if not isinstance(care, str) or care not in CARE_TYPES:
        raise ApiError(400, "care must be one of: " + ", ".join(CARE_TYPES))
    timestamp_field, interval_field, verb = CARE_TYPES[care]

    now = timestamps.now()
    with store.transaction():
        before = _live_room_plant(store, room_plant_id)
        plant = store.get_plant(before.plant_id)
        if plant is None or not getattr(plant, interval_field):
            raise ApiError(422, f"No {care} data for this plant")
        cared = before.model_copy(update={timestamp_field: now})
        _record(
            store,
            actor,
            cared,
            type_="care_done",
            text=f"{verb} the {_display_name(store, before)}",
            undo_payload=RestorePlantPayload(kind="restore_plant", room_plant=before),
            now=now,
        )
    live.notify(cared.room_id)
    return cared
