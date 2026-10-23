"""Remove soft-deleted gardens for good.

Run ``uv run python -m app.room_purge [--days N]``. It uses the configured database
(``FERNSLOP_DATABASE_URL``, see ``app/store.py``). A room deleted more than N days ago
(default 7) goes with its plants, areas, feed events, follows and the photos only its
posts used. Younger deletions and live rooms stay. Safe to run again: a purged room is gone.

It also deletes follows still unconfirmed 7 days after their ``created_at`` (the confirmation
window, #200/#207); confirmed and younger follows stay. ``--days`` does not change that window.
"""

import argparse
import sys
from datetime import timedelta

from app import timestamps
from app.routers.follows import CONFIRM_WINDOW
from app.store import get_store

RETENTION_DAYS = 7


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Purge rooms deleted more than N days ago.")
    parser.add_argument(
        "--days", type=float, default=RETENTION_DAYS, help=f"retention in days (default {RETENTION_DAYS})"
    )
    args = parser.parse_args(argv)

    store = get_store()
    now = timestamps.now()
    purged = store.purge_deleted_rooms(now - timedelta(days=args.days))  # type: ignore[attr-defined]
    print(f"Purged {purged} room(s)")
    expired = store.purge_unconfirmed_follows(now - CONFIRM_WINDOW)  # type: ignore[attr-defined]
    print(f"Purged {expired} unconfirmed follow(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
