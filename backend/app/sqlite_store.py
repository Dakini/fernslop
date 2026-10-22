"""The SQLite store: ``StoreProtocol`` backed by a file, using only stdlib ``sqlite3``.

Records are kept as JSON in a ``json`` column, next to the few columns that are
queried (room id, email, token, ...). A ``seq`` column gives insertion order,
and saving an existing id updates the row in place, so a replaced record keeps
its position just as in the in-memory ``Store``. Photos live in a BLOB column.

One connection per store object, used only while holding an RLock. That makes a
``transaction()`` exclusive within the process and lets a reader outside a
transaction wait instead of seeing half of one. ``BEGIN IMMEDIATE`` plus a busy
timeout does the same across several store objects or processes on one file.
"""

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app import timestamps
from app.models import FeedEvent, Plant, Room, RoomArea, RoomPlant, StoredFollow, StoredPhoto
from app.seed import build_seed

M = TypeVar("M", bound=BaseModel)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plants (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rooms (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS room_plants (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE, room_id TEXT NOT NULL, json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS room_plants_room ON room_plants (room_id);
CREATE TABLE IF NOT EXISTS areas (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE, room_id TEXT NOT NULL, json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS areas_room ON areas (room_id);
CREATE TABLE IF NOT EXISTS feed_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE, room_id TEXT NOT NULL,
    created_at TEXT NOT NULL, photo_url TEXT, json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS feed_events_room ON feed_events (room_id);
CREATE TABLE IF NOT EXISTS follows (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE, room_id TEXT NOT NULL,
    email_key TEXT NOT NULL, token TEXT NOT NULL, json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS follows_room ON follows (room_id);
CREATE INDEX IF NOT EXISTS follows_token ON follows (token);
CREATE TABLE IF NOT EXISTS photos (
    id TEXT PRIMARY KEY, url TEXT NOT NULL, content_type TEXT NOT NULL, created_at TEXT NOT NULL, data BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

_DATA_TABLES = ("plants", "rooms", "room_plants", "areas", "feed_events", "follows", "photos")


class SqliteStore:
    """Holds all application data in a SQLite file (created on first use)."""

    def __init__(self, path: str | Path, *, seed: bool = True) -> None:
        self._seed = seed
        self._lock = threading.RLock()
        self._depth = 0
        # isolation_level=None: autocommit, and transactions are begun by hand.
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None, timeout=30)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        with self.transaction():
            for statement in _SCHEMA.split(";"):
                if statement.strip():
                    self._db.execute(statement)
            if seed and self._db.execute("SELECT 1 FROM meta WHERE key = 'seeded'").fetchone() is None:
                self._load_seed()

    # --- Housekeeping ---------------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Exclusive and atomic: an exception rolls back every write in the block. Re-entrant."""
        with self._lock:
            if self._depth > 0:
                self._depth += 1
                try:
                    yield
                finally:
                    self._depth -= 1
                return
            self._db.execute("BEGIN IMMEDIATE")
            self._depth = 1
            try:
                yield
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            else:
                self._db.execute("COMMIT")
            finally:
                self._depth = 0

    def reset(self) -> None:
        """Discard everything and return to how this store was built (seeded or empty)."""
        with self.transaction():
            for table in _DATA_TABLES:
                self._db.execute(f"DELETE FROM {table}")
            self._db.execute("DELETE FROM meta")
            if self._seed:
                self._load_seed()

    def _load_seed(self) -> None:
        data = build_seed(timestamps.now())
        for plant in data.plants:
            self._save("plants", plant)
        for room in data.rooms:
            self._save("rooms", room)
        for room_plant in data.room_plants:
            self.save_room_plant(room_plant)
        for area in data.areas:
            self.save_area(area)
        for event in data.feed_events:
            self.save_feed_event(event)
        for photo in data.photos:
            self.save_photo(photo)
        for follow in data.follows:
            self.save_follow(follow)
        self._db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('seeded', '1')")

    # --- Helpers --------------------------------------------------------------

    def _save(self, table: str, record: BaseModel, **columns: object) -> None:
        values = {"id": record.id, **columns, "json": record.model_dump_json()}  # type: ignore[attr-defined]
        names = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        updates = ", ".join(f"{name} = excluded.{name}" for name in values if name != "id")
        with self._lock:
            # An upsert (not INSERT OR REPLACE) keeps the row, and so its position.
            self._db.execute(
                f"INSERT INTO {table} ({names}) VALUES ({marks}) ON CONFLICT(id) DO UPDATE SET {updates}",
                tuple(values.values()),
            )

    def _one(self, model: type[M], table: str, where: str, *args: object) -> M | None:
        with self._lock:
            row = self._db.execute(f"SELECT json FROM {table} WHERE {where} ORDER BY seq LIMIT 1", args).fetchone()
        return model.model_validate_json(row[0]) if row else None

    def _many(self, model: type[M], table: str, where: str = "1", *args: object, order: str = "seq") -> list[M]:
        with self._lock:
            rows = self._db.execute(f"SELECT json FROM {table} WHERE {where} ORDER BY {order}", args).fetchall()
        return [model.model_validate_json(row[0]) for row in rows]

    # --- Plants ---------------------------------------------------------------

    def list_plants(self) -> list[Plant]:
        return self._many(Plant, "plants")

    def get_plant(self, plant_id: str) -> Plant | None:
        return self._one(Plant, "plants", "id = ?", plant_id)

    # --- Rooms ----------------------------------------------------------------

    def list_rooms(self) -> list[Room]:
        return self._many(Room, "rooms")

    def get_room(self, room_id: str) -> Room | None:
        return self._one(Room, "rooms", "id = ?", room_id)

    def save_room(self, room: Room) -> None:
        self._save("rooms", room)

    # --- Room plants ----------------------------------------------------------

    def list_room_plants(self, room_id: str, *, include_deleted: bool = False) -> list[RoomPlant]:
        plants = self._many(RoomPlant, "room_plants", "room_id = ?", room_id)
        return [p for p in plants if include_deleted or p.deleted_at is None]

    def get_room_plant(self, room_plant_id: str) -> RoomPlant | None:
        return self._one(RoomPlant, "room_plants", "id = ?", room_plant_id)

    def save_room_plant(self, room_plant: RoomPlant) -> None:
        self._save("room_plants", room_plant, room_id=room_plant.room_id)

    # --- Areas ----------------------------------------------------------------

    def list_areas(self, room_id: str, *, include_deleted: bool = False) -> list[RoomArea]:
        areas = self._many(RoomArea, "areas", "room_id = ?", room_id)
        return [a for a in areas if include_deleted or a.deleted_at is None]

    def get_area(self, area_id: str) -> RoomArea | None:
        return self._one(RoomArea, "areas", "id = ?", area_id)

    def save_area(self, area: RoomArea) -> None:
        self._save("areas", area, room_id=area.room_id)

    # --- Feed -----------------------------------------------------------------

    def list_feed_events(self, room_id: str) -> list[FeedEvent]:
        """Newest first by ``created_at``; of two with the same timestamp, the later-saved first."""
        return self._many(FeedEvent, "feed_events", "room_id = ?", room_id, order="created_at DESC, seq DESC")

    def get_feed_event(self, event_id: str) -> FeedEvent | None:
        return self._one(FeedEvent, "feed_events", "id = ?", event_id)

    def save_feed_event(self, event: FeedEvent) -> None:
        self._save(
            "feed_events",
            event,
            room_id=event.room_id,
            created_at=_stamp(event.created_at),
            photo_url=event.photo_url,
        )

    # --- Follows --------------------------------------------------------------

    def list_follows(self, room_id: str) -> list[StoredFollow]:
        return self._many(StoredFollow, "follows", "room_id = ?", room_id)

    def get_follow_by_email(self, room_id: str, email: str) -> StoredFollow | None:
        return self._one(StoredFollow, "follows", "room_id = ? AND email_key = ?", room_id, email.casefold())

    def get_follow_by_token(self, token: str) -> StoredFollow | None:
        return self._one(StoredFollow, "follows", "token = ?", token)

    def save_follow(self, follow: StoredFollow) -> None:
        self._save(
            "follows",
            follow,
            room_id=follow.room_id,
            email_key=follow.email.casefold(),
            token=follow.unsubscribe_token,
        )

    def delete_follow(self, follow_id: str) -> bool:
        """Remove a follow. Returns whether one was removed; an unknown id is not an error."""
        with self._lock:
            return self._db.execute("DELETE FROM follows WHERE id = ?", (follow_id,)).rowcount > 0

    # --- Photos ---------------------------------------------------------------

    def get_photo(self, photo_id: str) -> StoredPhoto | None:
        with self._lock:
            row = self._db.execute(
                "SELECT id, url, content_type, created_at, data FROM photos WHERE id = ?", (photo_id,)
            ).fetchone()
        if row is None:
            return None
        return StoredPhoto(id=row[0], url=row[1], content_type=row[2], created_at=row[3], data=bytes(row[4]))

    def save_photo(self, photo: StoredPhoto) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO photos (id, url, content_type, created_at, data) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET url = excluded.url, content_type = excluded.content_type, "
                "created_at = excluded.created_at, data = excluded.data",
                (photo.id, photo.url, photo.content_type, _stamp(photo.created_at), photo.data),
            )

    def delete_unreferenced_photos(self, older_than: datetime) -> int:
        """Delete photos created before ``older_than`` that no feed event's ``photo_url`` points at.

        Returns how many were deleted. Not part of ``StoreProtocol``: only the cleanup command needs it.
        """
        with self.transaction():
            cursor = self._db.execute(
                "DELETE FROM photos WHERE created_at < ? "
                "AND NOT EXISTS (SELECT 1 FROM feed_events WHERE feed_events.photo_url = photos.url)",
                (_stamp(older_than),),
            )
            return cursor.rowcount


def _stamp(value: datetime) -> str:
    # Same form the API uses: fixed width, UTC, so strings sort like the times.
    return timestamps.format_timestamp(value)
