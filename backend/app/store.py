"""The store interface and the one place that picks the implementation.

Routers reach data only through the methods of ``StoreProtocol``; ``SqlStore``
(``app/sql_store.py``) implements it on SQLAlchemy. The store never raises "not
found" and never enforces room limits or business rules: lookups return ``None``
or an empty list, and routers decide the status code.

Rooms are soft-deleted (#196): ``delete_room`` sets ``deleted_at``, and from then on
``get_room`` and ``list_rooms`` act as if the room did not exist, so every room call
404s through the router's usual check. ``app.room_purge`` removes such rooms for good
after 7 days and ``app.room_restore`` brings one back before then.

Configuration: the database is the SQLAlchemy URL in the environment variable
``FERNSLOP_DATABASE_URL``. Unset, it is ``sqlite:///fernslop.db`` (a file in the
working directory, created on first use and ignored by git), so data survives
restarts. Example for another database: ``postgresql+psycopg://user:pw@host/db``
(the ``psycopg`` v3 driver is a dependency).
"""

import os
import threading
from collections.abc import Collection
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.models import (
    FeedEvent,
    Plant,
    Room,
    RoomArea,
    RoomPlant,
    StoredFollow,
    StoredPhoto,
)
from app.sql_store import SqlStore


@runtime_checkable
class StoreProtocol(Protocol):
    """Everything the routers may ask of a store."""

    # Plants
    def list_plants(self) -> list[Plant]: ...
    def get_plant(self, plant_id: str) -> Plant | None: ...
    def get_plants(self, plant_ids: Collection[str]) -> list[Plant]: ...

    # Rooms
    def list_rooms(self) -> list[Room]: ...
    def get_room(self, room_id: str) -> Room | None: ...
    def save_room(self, room: Room) -> None: ...
    def delete_room(self, room_id: str, deleted_at: datetime) -> bool: ...

    # Room plants
    def list_room_plants(self, room_id: str, *, include_deleted: bool = False) -> list[RoomPlant]: ...
    def list_room_plants_in(self, room_ids: Collection[str]) -> list[RoomPlant]: ...
    def get_room_plant(self, room_plant_id: str) -> RoomPlant | None: ...
    def save_room_plant(self, room_plant: RoomPlant) -> None: ...

    # Areas
    def list_areas(self, room_id: str, *, include_deleted: bool = False) -> list[RoomArea]: ...
    def list_areas_in(self, room_ids: Collection[str]) -> list[RoomArea]: ...
    def get_area(self, area_id: str) -> RoomArea | None: ...
    def save_area(self, area: RoomArea) -> None: ...

    # Feed
    def list_feed_events(self, room_id: str) -> list[FeedEvent]: ...
    def get_feed_event(self, event_id: str) -> FeedEvent | None: ...
    def photo_url_in_feed(self, url: str) -> bool: ...
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
    def photo_storage_bytes(self) -> int: ...

    # Housekeeping
    def ping(self) -> None: ...
    def transaction(self) -> AbstractContextManager[None]: ...
    def reset(self) -> None: ...


DATABASE_URL_ENV = "FERNSLOP_DATABASE_URL"
DEFAULT_DATABASE_URL = "sqlite:///fernslop.db"

_stores: dict[str, SqlStore] = {}
_stores_lock = threading.Lock()


def get_store() -> StoreProtocol:
    """FastAPI dependency that returns the store: one ``SqlStore`` per configured URL, built on first use."""
    url = os.environ.get(DATABASE_URL_ENV) or DEFAULT_DATABASE_URL
    with _stores_lock:
        if url not in _stores:
            _stores[url] = SqlStore(url)
        return _stores[url]


def close_stores() -> None:
    """Forget the cached stores and close their connections (the next ``get_store()`` builds a new one)."""
    with _stores_lock:
        for store in _stores.values():
            store.dispose()
        _stores.clear()
