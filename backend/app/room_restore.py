"""Bring back a soft-deleted garden before it is purged.

Run ``uv run python -m app.room_restore --list`` to see deleted rooms, and
``uv run python -m app.room_restore <room id>`` to restore one with its plants, areas,
feed and follows. It uses the configured database (``FERNSLOP_DATABASE_URL``, see
``app/store.py``). An unknown, live or already purged id exits 1 and changes nothing.
"""

import argparse
import sys

from app import timestamps
from app.store import get_store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List or restore soft-deleted rooms.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="list deleted rooms")
    group.add_argument("room_id", nargs="?", help="the id of the deleted room to restore")
    args = parser.parse_args(argv)

    store = get_store()
    if args.list:
        rooms = store.list_deleted_rooms()  # type: ignore[attr-defined]
        for room in rooms:
            print(f"{room.id}\t{room.name}\tdeleted at {timestamps.format_timestamp(room.deleted_at)}")
        if not rooms:
            print("No deleted rooms")
        return 0

    if not store.restore_room(args.room_id):  # type: ignore[attr-defined]
        print(f"No deleted room with id {args.room_id} (unknown, not deleted, or already purged)", file=sys.stderr)
        return 1
    print(f"Restored room {args.room_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
