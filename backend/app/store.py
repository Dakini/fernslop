"""The in-memory store.

Routers reach data only through the methods of ``StoreProtocol``, so a
database-backed implementation (issue 015) can replace ``Store`` without
touching them. The store never raises "not found" and never enforces room
limits or business rules: lookups return ``None`` or an empty list, and routers
decide the status code.
"""

import threading
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from app import timestamps
from app.models import FeedEvent, Plant, Room, RoomArea, RoomPlant, StoredFollow, StoredPhoto
from app.seed import build_seed

M = TypeVar("M", bound=BaseModel)


@runtime_checkable
class StoreProtocol(Protocol):
    """Everything the routers may ask of a store."""

    # Plants
    def list_plants(self) -> list[Plant]: ...
    def get_plant(self, plant_id: str) -> Plant | None: ...

    # Rooms
    def list_rooms(self) -> list[Room]: ...
    def get_room(self, room_id: str) -> Room | None: ...
    def save_room(self, room: Room) -> None: ...

    # Room plants
    def list_room_plants(self, room_id: str, *, include_deleted: bool = False) -> list[RoomPlant]: ...
    def get_room_plant(self, room_plant_id: str) -> RoomPlant | None: ...
    def save_room_plant(self, room_plant: RoomPlant) -> None: ...

    # Areas
    def list_areas(self, room_id: str, *, include_deleted: bool = False) -> list[RoomArea]: ...
    def get_area(self, area_id: str) -> RoomArea | None: ...
    def save_area(self, area: RoomArea) -> None: ...

    # Feed
    def list_feed_events(self, room_id: str) -> list[FeedEvent]: ...
    def get_feed_event(self, event_id: str) -> FeedEvent | None: ...
    def save_feed_event(self, event: FeedEvent) -> None: ...

    # Follows
    def list_follows(self, room_id: str) -> list[StoredFollow]: ...
    def get_follow_by_email(self, room_id: str, email: str) -> StoredFollow | None: ...
    def get_follow_by_token(self, token: str) -> StoredFollow | None: ...
    def save_follow(self, follow: StoredFollow) -> None: ...
    def delete_follow(self, follow_id: str) -> bool: ...

    # Photos
    def get_photo(self, photo_id: str) -> StoredPhoto | None: ...
    def save_photo(self, photo: StoredPhoto) -> None: ...

    # Housekeeping
    def transaction(self) -> AbstractContextManager[None]: ...
    def reset(self) -> None: ...


def _copy(record: M) -> M:
    return record.model_copy(deep=True)


class Store:
    """Holds all application data in memory.

    Records are copied on the way in and on the way out, so mutating an object
    never changes the store until it is passed to a ``save_*`` method.
    """

    def __init__(self, *, seed: bool = True) -> None:
        self._seed = seed
        self._lock = threading.RLock()
        self.reset()

    def _clear(self) -> None:
        # Dicts keep insertion order, and replacing a value keeps its position.
        self._plants: dict[str, Plant] = {}
        self._rooms: dict[str, Room] = {}
        self._room_plants: dict[str, RoomPlant] = {}
        self._areas: dict[str, RoomArea] = {}
        self._feed_events: dict[str, FeedEvent] = {}
        self._follows: dict[str, StoredFollow] = {}
        self._photos: dict[str, StoredPhoto] = {}

    # --- Housekeeping ---------------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Hold the store lock. Re-entrant; it does not roll back on error."""
        with self._lock:
            yield

    def reset(self) -> None:
        """Discard everything and return to how this store was built (seeded or empty)."""
        with self._lock:
            self._clear()
            if not self._seed:
                return
            data = build_seed(timestamps.now())
            for plant in data.plants:
                self._plants[plant.id] = plant
            for room in data.rooms:
                self._rooms[room.id] = room
            for room_plant in data.room_plants:
                self._room_plants[room_plant.id] = room_plant
            for area in data.areas:
                self._areas[area.id] = area
            for event in data.feed_events:
                self._feed_events[event.id] = event
            for photo in data.photos:
                self._photos[photo.id] = photo
            for follow in data.follows:
                self._follows[follow.id] = follow

    # --- Plants ---------------------------------------------------------------

    def list_plants(self) -> list[Plant]:
        with self._lock:
            return [_copy(plant) for plant in self._plants.values()]

    def get_plant(self, plant_id: str) -> Plant | None:
        with self._lock:
            plant = self._plants.get(plant_id)
            return _copy(plant) if plant else None

    # --- Rooms ----------------------------------------------------------------

    def list_rooms(self) -> list[Room]:
        with self._lock:
            return [_copy(room) for room in self._rooms.values()]

    def get_room(self, room_id: str) -> Room | None:
        with self._lock:
            room = self._rooms.get(room_id)
            return _copy(room) if room else None

    def save_room(self, room: Room) -> None:
        with self._lock:
            self._rooms[room.id] = _copy(room)

    # --- Room plants ----------------------------------------------------------

    def list_room_plants(self, room_id: str, *, include_deleted: bool = False) -> list[RoomPlant]:
        with self._lock:
            return [
                _copy(room_plant)
                for room_plant in self._room_plants.values()
                if room_plant.room_id == room_id and (include_deleted or room_plant.deleted_at is None)
            ]

    def get_room_plant(self, room_plant_id: str) -> RoomPlant | None:
        with self._lock:
            room_plant = self._room_plants.get(room_plant_id)
            return _copy(room_plant) if room_plant else None

    def save_room_plant(self, room_plant: RoomPlant) -> None:
        with self._lock:
            self._room_plants[room_plant.id] = _copy(room_plant)

    # --- Areas ----------------------------------------------------------------

    def list_areas(self, room_id: str, *, include_deleted: bool = False) -> list[RoomArea]:
        with self._lock:
            return [
                _copy(area)
                for area in self._areas.values()
                if area.room_id == room_id and (include_deleted or area.deleted_at is None)
            ]

    def get_area(self, area_id: str) -> RoomArea | None:
        with self._lock:
            area = self._areas.get(area_id)
            return _copy(area) if area else None

    def save_area(self, area: RoomArea) -> None:
        with self._lock:
            self._areas[area.id] = _copy(area)

    # --- Feed -----------------------------------------------------------------

    def list_feed_events(self, room_id: str) -> list[FeedEvent]:
        """Newest first by ``created_at``; of two with the same timestamp, the later-saved first."""
        with self._lock:
            events = [event for event in self._feed_events.values() if event.room_id == room_id]
            # Reversing first makes the stable, descending sort put later-saved events ahead on ties.
            events.reverse()
            events.sort(key=lambda event: event.created_at, reverse=True)
            return [_copy(event) for event in events]

    def get_feed_event(self, event_id: str) -> FeedEvent | None:
        with self._lock:
            event = self._feed_events.get(event_id)
            return _copy(event) if event else None

    def save_feed_event(self, event: FeedEvent) -> None:
        with self._lock:
            self._feed_events[event.id] = _copy(event)

    # --- Follows --------------------------------------------------------------

    def list_follows(self, room_id: str) -> list[StoredFollow]:
        with self._lock:
            return [_copy(follow) for follow in self._follows.values() if follow.room_id == room_id]

    def get_follow_by_email(self, room_id: str, email: str) -> StoredFollow | None:
        wanted = email.casefold()
        with self._lock:
            for follow in self._follows.values():
                if follow.room_id == room_id and follow.email.casefold() == wanted:
                    return _copy(follow)
            return None

    def get_follow_by_token(self, token: str) -> StoredFollow | None:
        with self._lock:
            for follow in self._follows.values():
                if follow.unsubscribe_token == token:
                    return _copy(follow)
            return None

    def save_follow(self, follow: StoredFollow) -> None:
        with self._lock:
            self._follows[follow.id] = _copy(follow)

    def delete_follow(self, follow_id: str) -> bool:
        """Remove a follow. Returns whether one was removed; an unknown id is not an error."""
        with self._lock:
            return self._follows.pop(follow_id, None) is not None

    # --- Photos ---------------------------------------------------------------

    def get_photo(self, photo_id: str) -> StoredPhoto | None:
        with self._lock:
            photo = self._photos.get(photo_id)
            return _copy(photo) if photo else None

    def save_photo(self, photo: StoredPhoto) -> None:
        with self._lock:
            self._photos[photo.id] = _copy(photo)


store = Store()


def get_store() -> StoreProtocol:
    """FastAPI dependency that returns the store. The one place that picks the implementation."""
    return store
