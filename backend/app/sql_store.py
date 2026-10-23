"""The database store: ``StoreProtocol`` on SQLAlchemy Core.

The database is chosen by a SQLAlchemy URL (see ``get_store`` in ``store.py``), so
any database SQLAlchemy supports can back it. Only portable types and statements
are used: the schema is built with ``create_all`` and saving is select-then-insert-or-update.

Records are kept as JSON in a ``json`` column, next to the few columns that are
queried (room id, email, token, ...). A ``seq`` column gives insertion order, and
saving an existing id updates the row in place, so a replaced record keeps its
position. Photos live in a binary column.

One lock per store object. ``transaction()`` holds it together with one database
transaction on one connection, so it is exclusive within the process and a reader
outside a transaction waits instead of seeing half of one. Across processes the
database takes over: on SQLite ``BEGIN IMMEDIATE`` plus a busy timeout, on PostgreSQL a
transaction-level advisory lock taken as each transaction begins (so creating the tables and
seeding an empty database is safe for stores starting at the same moment).
"""

import threading
from collections.abc import Collection, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import (
    Column,
    Connection,
    Engine,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    event,
    exists,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool, StaticPool

from app import timestamps
from app.models import (
    FeedEvent,
    Plant,
    Room,
    RoomArea,
    RoomPlant,
    StoredFollow,
    StoredPhoto,
    StoredRoom,
)
from app.seed import build_seed

M = TypeVar("M", bound=BaseModel)

# --- Schema ---------------------------------------------------------------------

_ID = String(255)
_TIMESTAMP = String(40)  # fixed-width UTC strings (see ``_stamp``), so they sort like the times

_metadata = MetaData()


def _records(name: str, *columns: Column) -> Table:
    """A table of JSON records in insertion order (``seq``), with a few extra queryable columns."""
    return Table(
        name,
        _metadata,
        Column("seq", Integer, primary_key=True, autoincrement=True),
        Column("id", _ID, nullable=False, unique=True),
        *columns,
        Column("json", Text, nullable=False),
    )


_plants = _records("plants")
_rooms = _records("rooms")
_room_plants = _records("room_plants", Column("room_id", _ID, nullable=False, index=True))
_areas = _records("areas", Column("room_id", _ID, nullable=False, index=True))
_feed_events = _records(
    "feed_events",
    Column("room_id", _ID, nullable=False, index=True),
    Column("created_at", _TIMESTAMP, nullable=False),
    Column("photo_url", Text, nullable=True, index=True),
)
_follows = _records(
    "follows",
    Column("room_id", _ID, nullable=False, index=True),
    Column("email_key", _ID, nullable=False),
    Column("token", _ID, nullable=False, index=True),
)
_photos = Table(
    "photos",
    _metadata,
    Column("id", _ID, primary_key=True),
    Column("url", Text, nullable=False),
    Column("content_type", String(100), nullable=False),
    Column("created_at", _TIMESTAMP, nullable=False),
    Column("data", LargeBinary, nullable=False),
)
_meta = Table("meta", _metadata, Column("key", String(100), primary_key=True), Column("value", Text, nullable=False))

_DATA_TABLES = (_plants, _rooms, _room_plants, _areas, _feed_events, _follows, _photos, _meta)


# --- Connection setup -----------------------------------------------------------

_POSTGRES_LOCK_KEY = 7_130_001  # arbitrary; the advisory lock key every Fernslop transaction takes
PING_TIMEOUT_SECONDS = 3  # connecting to PostgreSQL, and the health check's SELECT 1


def _make_engine(url: str) -> Engine:
    """The one place that knows about database quirks (SQLite, PostgreSQL); others get a plain engine."""
    parsed = make_url(url)
    backend = parsed.get_backend_name()
    if backend == "postgresql":
        return _make_postgres_engine(url)
    if backend != "sqlite":
        return create_engine(url)

    options: dict = {"connect_args": {"check_same_thread": False, "timeout": 30}}
    if parsed.database in (None, "", ":memory:"):
        # One shared connection, so every method sees the same in-memory database.
        options["poolclass"] = StaticPool
    engine = create_engine(url, **options)

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _record):
        # Take over transaction control from pysqlite (see the SQLAlchemy "serializable isolation" recipe).
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(connection):
        # Take the write lock up front, so a transaction never fails halfway with "database is locked".
        connection.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


def _make_postgres_engine(url: str) -> Engine:
    # pre-ping replaces connections the server or a proxy has closed while idle in the pool.
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": PING_TIMEOUT_SECONDS})

    @event.listens_for(engine, "begin")
    def _on_begin(connection):
        # The counterpart of SQLite's BEGIN IMMEDIATE: one transaction at a time across all processes.
        # The lock is released by the database when the transaction ends, however it ends.
        connection.exec_driver_sql(f"SELECT pg_advisory_xact_lock({_POSTGRES_LOCK_KEY})")

    return engine


def _make_ping_engine(url: str) -> Engine:
    """A bare engine for ``SqlStore.ping``: no pool, no lock-taking ``begin`` hook, timeouts on PostgreSQL.

    Every ping opens a fresh connection, so libpq's ``connect_timeout`` bounds the whole handshake even when the
    server accepts the TCP connection but never answers (a pooled connection would wait on it forever).
    """
    connect_args: dict = {}
    if make_url(url).get_backend_name() == "postgresql":
        connect_args = {
            "connect_timeout": PING_TIMEOUT_SECONDS,
            "options": f"-c statement_timeout={PING_TIMEOUT_SECONDS * 1000}",
        }
    return create_engine(url, poolclass=NullPool, connect_args=connect_args)


def _stamp(value: datetime) -> str:
    # Same form the API uses: fixed width, UTC, so strings sort like the times.
    return timestamps.format_timestamp(value)


# --- The store ------------------------------------------------------------------


class SqlStore:
    """Holds all application data in the database at ``url`` (tables are created on first use)."""

    def __init__(self, url: str, *, seed: bool = True) -> None:
        self._seed = seed
        self._lock = threading.RLock()
        self._conn: Connection | None = None  # the open transaction's connection, if any
        self._engine = _make_engine(url)
        self._ping_engine = _make_ping_engine(url)
        with self._tx() as conn:
            _metadata.create_all(conn)
            if seed and conn.execute(select(_meta.c.key).where(_meta.c.key == "seeded")).first() is None:
                self._load_seed()

    def dispose(self) -> None:
        """Close the pooled connections. The store must not be used afterwards."""
        self._engine.dispose()
        self._ping_engine.dispose()

    # --- Housekeeping -----------------------------------------------------------

    def ping(self) -> None:
        """Run ``SELECT 1``; raises when the database does not answer within a few seconds.

        Takes neither the store lock nor PostgreSQL's advisory lock (nor SQLite's write lock): it runs on its
        own short-lived connection from an engine without the lock hooks, so a long transaction cannot stall it.
        On in-memory SQLite that connection sees a separate, empty database, which is fine for ``SELECT 1``.
        """
        with self._ping_engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1").scalar_one()

    def transaction(self) -> AbstractContextManager[None]:
        """Exclusive and atomic: an exception rolls back every write in the block. Re-entrant.

        Nested blocks join the outermost one, which alone decides commit or rollback.
        """
        return self._tx()

    @contextmanager
    def _tx(self) -> Iterator[Connection]:
        """``transaction()`` that also hands out the connection; without an open one, a short transaction."""
        with self._lock:
            if self._conn is not None:
                yield self._conn
                return
            with self._engine.begin() as conn:  # commits on success, rolls back on any exception
                self._conn = conn
                try:
                    yield conn
                finally:
                    self._conn = None

    def reset(self) -> None:
        """Discard everything and return to how this store was built (seeded or empty)."""
        with self._tx() as conn:
            for table in _DATA_TABLES:
                conn.execute(delete(table))
            if self._seed:
                self._load_seed()

    def _load_seed(self) -> None:
        data = build_seed(timestamps.now())
        for plant in data.plants:
            self._save(_plants, plant)
        for room in data.rooms:
            self.save_room(room)
        for room_plant in data.room_plants:
            self.save_room_plant(room_plant)
        for area in data.areas:
            self.save_area(area)
        for event_ in data.feed_events:
            self.save_feed_event(event_)
        for photo in data.photos:
            self.save_photo(photo)
        for follow in data.follows:
            self.save_follow(follow)
        with self._tx() as conn:
            _upsert(conn, _meta, "key", {"key": "seeded", "value": "1"})

    # --- Helpers ----------------------------------------------------------------

    def _save(self, table: Table, record: BaseModel, **columns: object) -> None:
        values = {"id": record.id, **columns, "json": record.model_dump_json()}  # type: ignore[attr-defined]
        with self._tx() as conn:
            _upsert(conn, table, "id", values)

    def _one(self, model: type[M], table: Table, *where) -> M | None:
        with self._tx() as conn:
            text = conn.execute(select(table.c.json).where(*where).order_by(table.c.seq).limit(1)).scalar()
        return model.model_validate_json(text) if text is not None else None

    def _many(self, model: type[M], table: Table, *where, order=None) -> list[M]:
        order = (table.c.seq,) if order is None else order
        with self._tx() as conn:
            rows = conn.execute(select(table.c.json).where(*where).order_by(*order)).scalars().all()
        return [model.model_validate_json(text) for text in rows]

    # --- Plants -----------------------------------------------------------------

    def list_plants(self) -> list[Plant]:
        return self._many(Plant, _plants)

    def get_plant(self, plant_id: str) -> Plant | None:
        return self._one(Plant, _plants, _plants.c.id == plant_id)

    def get_plants(self, plant_ids: Collection[str]) -> list[Plant]:
        """The plants with these ids, in one query (unknown ids are skipped)."""
        return self._many(Plant, _plants, _plants.c.id.in_(set(plant_ids))) if plant_ids else []

    # --- Rooms ------------------------------------------------------------------

    def _stored_rooms(self, *where) -> list[StoredRoom]:
        """Every stored room, live and soft-deleted. The one place that reads room rows."""
        return self._many(StoredRoom, _rooms, *where)

    def _live_rooms(self, *where) -> list[Room]:
        """The one place soft-deleted rooms are filtered out: routers only ever see these."""
        return [
            Room.model_validate(room.model_dump(exclude={"deleted_at"}))
            for room in self._stored_rooms(*where)
            if room.deleted_at is None
        ]

    def list_rooms(self) -> list[Room]:
        return self._live_rooms()

    def get_room(self, room_id: str) -> Room | None:
        rooms = self._live_rooms(_rooms.c.id == room_id)
        return rooms[0] if rooms else None

    def save_room(self, room: Room) -> None:
        self._save(_rooms, room)

    def delete_room(self, room_id: str, deleted_at: datetime) -> bool:
        """Soft-delete a live room: set its ``deleted_at`` and keep everything else.

        Returns whether this call marked it (``False`` for an unknown or already deleted room).
        """
        with self._tx():
            room = self.get_room(room_id)
            if room is None:
                return False
            self._save(_rooms, StoredRoom(**room.model_dump(), deleted_at=deleted_at))
            return True

    # Not part of ``StoreProtocol``: only the purge and restore commands use these.

    def list_deleted_rooms(self) -> list[StoredRoom]:
        """Soft-deleted rooms, oldest deletion first."""
        deleted = [room for room in self._stored_rooms() if room.deleted_at is not None]
        return sorted(deleted, key=lambda room: room.deleted_at)  # type: ignore[arg-type, return-value]

    def restore_room(self, room_id: str) -> bool:
        """Clear a soft-deleted room's ``deleted_at``. Returns ``False`` for an unknown, live or purged id."""
        with self._tx():
            rooms = self._stored_rooms(_rooms.c.id == room_id)
            if not rooms or rooms[0].deleted_at is None:
                return False
            self._save(_rooms, rooms[0].model_copy(update={"deleted_at": None}))
            return True

    def purge_deleted_rooms(self, deleted_before: datetime) -> int:
        """Hard-delete every room soft-deleted before ``deleted_before``, in one transaction. Returns how many."""
        with self._tx():
            due = [room.id for room in self.list_deleted_rooms() if room.deleted_at < deleted_before]  # type: ignore[operator]
            for room_id in due:
                self._hard_delete_room(room_id)
            return len(due)

    def _hard_delete_room(self, room_id: str) -> None:
        """Remove a room with its plants, areas, feed events and follows.

        Photos that only this room's feed events point at go too; a photo another room's event also
        points at, or one no event points at, stays.
        """
        with self._tx() as conn:
            conn.execute(delete(_rooms).where(_rooms.c.id == room_id))
            photo_urls = (
                conn.execute(
                    select(_feed_events.c.photo_url).where(
                        _feed_events.c.room_id == room_id, _feed_events.c.photo_url.is_not(None)
                    )
                )
                .scalars()
                .all()
            )
            for table in (_room_plants, _areas, _feed_events, _follows):
                conn.execute(delete(table).where(table.c.room_id == room_id))
            if photo_urls:
                still_used = exists().where(_feed_events.c.photo_url == _photos.c.url)
                conn.execute(delete(_photos).where(_photos.c.url.in_(set(photo_urls)), ~still_used))

    # --- Room plants ------------------------------------------------------------

    def list_room_plants(self, room_id: str, *, include_deleted: bool = False) -> list[RoomPlant]:
        plants = self._many(RoomPlant, _room_plants, _room_plants.c.room_id == room_id)
        return [p for p in plants if include_deleted or p.deleted_at is None]

    def list_room_plants_in(self, room_ids: Collection[str]) -> list[RoomPlant]:
        """Live plants of all these rooms, in one query."""
        if not room_ids:
            return []
        plants = self._many(RoomPlant, _room_plants, _room_plants.c.room_id.in_(set(room_ids)))
        return [p for p in plants if p.deleted_at is None]

    def get_room_plant(self, room_plant_id: str) -> RoomPlant | None:
        return self._one(RoomPlant, _room_plants, _room_plants.c.id == room_plant_id)

    def save_room_plant(self, room_plant: RoomPlant) -> None:
        self._save(_room_plants, room_plant, room_id=room_plant.room_id)

    # --- Areas ------------------------------------------------------------------

    def list_areas(self, room_id: str, *, include_deleted: bool = False) -> list[RoomArea]:
        areas = self._many(RoomArea, _areas, _areas.c.room_id == room_id)
        return [a for a in areas if include_deleted or a.deleted_at is None]

    def list_areas_in(self, room_ids: Collection[str]) -> list[RoomArea]:
        """Live areas of all these rooms, in one query."""
        if not room_ids:
            return []
        areas = self._many(RoomArea, _areas, _areas.c.room_id.in_(set(room_ids)))
        return [a for a in areas if a.deleted_at is None]

    def get_area(self, area_id: str) -> RoomArea | None:
        return self._one(RoomArea, _areas, _areas.c.id == area_id)

    def save_area(self, area: RoomArea) -> None:
        self._save(_areas, area, room_id=area.room_id)

    # --- Feed -------------------------------------------------------------------

    def list_feed_events(self, room_id: str) -> list[FeedEvent]:
        """Newest first by ``created_at``; of two with the same timestamp, the later-saved first."""
        return self._many(
            FeedEvent,
            _feed_events,
            _feed_events.c.room_id == room_id,
            order=(_feed_events.c.created_at.desc(), _feed_events.c.seq.desc()),
        )

    def get_feed_event(self, event_id: str) -> FeedEvent | None:
        return self._one(FeedEvent, _feed_events, _feed_events.c.id == event_id)

    def photo_url_in_feed(self, url: str) -> bool:
        """Whether any feed event shows this photo: one ``EXISTS`` query, undone events and deleted rooms included."""
        with self._tx() as conn:
            return bool(conn.execute(select(exists().where(_feed_events.c.photo_url == url))).scalar_one())

    def save_feed_event(self, event: FeedEvent) -> None:
        self._save(
            _feed_events,
            event,
            room_id=event.room_id,
            created_at=_stamp(event.created_at),
            photo_url=event.photo_url,
        )

    # --- Follows ----------------------------------------------------------------

    def list_follows(self, room_id: str) -> list[StoredFollow]:
        return self._many(StoredFollow, _follows, _follows.c.room_id == room_id)

    def get_follow_by_email(self, room_id: str, email: str) -> StoredFollow | None:
        return self._one(
            StoredFollow, _follows, _follows.c.room_id == room_id, _follows.c.email_key == email.casefold()
        )

    def get_follow_by_token(self, token: str) -> StoredFollow | None:
        return self._one(StoredFollow, _follows, _follows.c.token == token)

    def save_follow(self, follow: StoredFollow) -> None:
        self._save(
            _follows,
            follow,
            room_id=follow.room_id,
            email_key=follow.email.casefold(),
            token=follow.unsubscribe_token,
        )

    def delete_follow(self, follow_id: str) -> bool:
        """Remove a follow. Returns whether one was removed; an unknown id is not an error."""
        with self._tx() as conn:
            return conn.execute(delete(_follows).where(_follows.c.id == follow_id)).rowcount > 0

    # --- Photos -----------------------------------------------------------------

    def get_photo(self, photo_id: str) -> StoredPhoto | None:
        with self._tx() as conn:
            row = conn.execute(select(_photos).where(_photos.c.id == photo_id)).first()
        if row is None:
            return None
        return StoredPhoto(
            id=row.id, url=row.url, content_type=row.content_type, created_at=row.created_at, data=bytes(row.data)
        )

    def save_photo(self, photo: StoredPhoto) -> None:
        values = {
            "id": photo.id,
            "url": photo.url,
            "content_type": photo.content_type,
            "created_at": _stamp(photo.created_at),
            "data": photo.data,
        }
        with self._tx() as conn:
            _upsert(conn, _photos, "id", values)

    def photo_storage_bytes(self) -> int:
        """Total size of the stored photo bytes, summed in the database (no photo is loaded)."""
        with self._tx() as conn:
            return int(conn.execute(select(func.coalesce(func.sum(func.length(_photos.c.data)), 0))).scalar_one())

    def delete_unreferenced_photos(self, older_than: datetime) -> int:
        """Delete photos created before ``older_than`` that no feed event's ``photo_url`` points at.

        Returns how many were deleted. Not part of ``StoreProtocol``: only the cleanup command needs it.
        """
        referenced = exists().where(_feed_events.c.photo_url == _photos.c.url)
        with self._tx() as conn:
            return conn.execute(delete(_photos).where(_photos.c.created_at < _stamp(older_than), ~referenced)).rowcount


def _upsert(conn: Connection, table: Table, key: str, values: dict) -> None:
    """Insert, or update the row with the same key in place (so it keeps its ``seq``).

    Select-then-write is portable; callers hold the store lock and an open transaction.
    """
    column = table.c[key]
    if conn.execute(select(column).where(column == values[key])).first() is None:
        conn.execute(insert(table).values(**values))
    else:
        conn.execute(update(table).where(column == values[key]).values(**{k: v for k, v in values.items() if k != key}))
