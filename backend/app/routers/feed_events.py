"""Feed events: undo.

Undoing applies the event's ``undo_payload`` (written by the room-plant and area
routers) and sets ``undone_at``. It keeps the payload, writes no new feed event,
bumps the room's ``last_activity_at`` to ``undone_at``, and calls ``live.notify``
once after the store transaction has ended. Every check runs before the first
write, so a 409 changes nothing. An event can only be undone while no later,
not-undone event touches the same plant or area, so an undo never silently
reverts a later change.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app import live, timestamps
from app.auth import Actor, get_actor
from app.errors import ApiError
from app.models import (
    DeletePlantPayload,
    FeedEvent,
    RestoreAreaPayload,
    RestorePlantPayload,
)
from app.rate_limit import WRITE, rate_limited
from app.routers.areas import MAX_LIVE_AREAS, TOO_MANY_AREAS_MESSAGE
from app.routers.room_plants import GARDEN_FULL_MESSAGE, MAX_LIVE_PLANTS
from app.store import StoreProtocol, get_store

router = APIRouter(tags=["Feed"])

EVENT_NOT_FOUND_MESSAGE = "Event not found"
CANNOT_UNDO_MESSAGE = "This can't be undone"
ALREADY_UNDONE_MESSAGE = "Already undone"
LATER_PLANT_CHANGES_MESSAGE = "Undo the later changes to this plant first"
LATER_AREA_CHANGES_MESSAGE = "Undo the later changes to this area first"


def _target(event: FeedEvent) -> tuple[str, str] | None:
    """The plant or area an event's undo writes to, or ``None`` for an event with no undo (a post)."""
    payload = event.undo_payload
    if isinstance(payload, RestorePlantPayload):
        return ("plant", payload.room_plant.id)
    if isinstance(payload, DeletePlantPayload):
        return ("plant", payload.room_plant_id)
    if isinstance(payload, RestoreAreaPayload):
        return ("area", payload.area_id)
    return None


def _check_no_later_changes(store: StoreProtocol, event: FeedEvent) -> None:
    """Refuse an undo that would silently revert a later, not-undone event for the same plant or area.

    Feed order is newest first (``created_at``, then save order), so every event
    listed before this one is later.
    """
    target = _target(event)
    for other in store.list_feed_events(event.room_id):
        if other.id == event.id:
            return
        if other.undone_at is None and _target(other) == target:
            kind = target[0]
            raise ApiError(409, LATER_PLANT_CHANGES_MESSAGE if kind == "plant" else LATER_AREA_CHANGES_MESSAGE)


def _check_room_for_plant(store: StoreProtocol, payload: RestorePlantPayload) -> None:
    snapshot = payload.room_plant
    current = store.get_room_plant(snapshot.id)
    comes_back = snapshot.deleted_at is None and (current is None or current.deleted_at is not None)
    if comes_back and len(store.list_room_plants(snapshot.room_id)) >= MAX_LIVE_PLANTS:
        raise ApiError(409, GARDEN_FULL_MESSAGE)


def _check_room_for_area(store: StoreProtocol, payload: RestoreAreaPayload) -> None:
    snapshot = payload.area
    if snapshot is None:
        return
    current = store.get_area(snapshot.id)
    comes_back = snapshot.deleted_at is None and (current is None or current.deleted_at is not None)
    if comes_back and len(store.list_areas(snapshot.room_id)) >= MAX_LIVE_AREAS:
        raise ApiError(409, TOO_MANY_AREAS_MESSAGE)


def _apply(store: StoreProtocol, event: FeedEvent, now) -> None:
    """Write the event's payload to the store. Call inside a transaction, after every check."""
    payload = event.undo_payload
    if isinstance(payload, RestorePlantPayload):
        store.save_room_plant(payload.room_plant)
    elif isinstance(payload, DeletePlantPayload):
        room_plant = store.get_room_plant(payload.room_plant_id)
        if room_plant is not None and room_plant.deleted_at is None:
            store.save_room_plant(room_plant.model_copy(update={"deleted_at": now}))
    elif isinstance(payload, RestoreAreaPayload):
        if payload.area is not None:
            store.save_area(payload.area)
        else:
            area = store.get_area(payload.area_id)
            if area is not None and area.deleted_at is None:
                store.save_area(area.model_copy(update={"deleted_at": now}))


@router.post("/feed-events/{event_id}/undo", operation_id="undoEvent", status_code=204, dependencies=[rate_limited(WRITE)])
def undo_event(
    event_id: str,
    store: Annotated[StoreProtocol, Depends(get_store)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> Response:
    now = timestamps.now()
    with store.transaction():
        event = store.get_feed_event(event_id)
        room = store.get_room(event.room_id) if event else None
        if event is None or room is None:
            raise ApiError(404, EVENT_NOT_FOUND_MESSAGE)
        if event.undone_at is not None:
            raise ApiError(409, ALREADY_UNDONE_MESSAGE)
        payload = event.undo_payload
        if payload is None:
            raise ApiError(409, CANNOT_UNDO_MESSAGE)
        _check_no_later_changes(store, event)

        if isinstance(payload, RestorePlantPayload):
            _check_room_for_plant(store, payload)
        elif isinstance(payload, RestoreAreaPayload):
            _check_room_for_area(store, payload)

        _apply(store, event, now)
        store.save_feed_event(event.model_copy(update={"undone_at": now}))
        room.last_activity_at = now
        store.save_room(room)
    live.notify(room.id)
    return Response(status_code=204)
