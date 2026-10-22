"""Delete uploaded photos that were never posted.

Run ``uv run python -m app.photo_cleanup [--hours N]``. Needs ``FERNSLOP_DB_PATH``:
the in-memory store has nothing to clean after a restart. A photo goes if it is
older than N hours (default 24) and no feed event's ``photo_url`` points at it.
"""

import argparse
import os
import sys
from datetime import timedelta

from app import timestamps
from app.store import DB_PATH_ENV, get_store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Delete photos older than N hours that no post uses.")
    parser.add_argument("--hours", type=float, default=24, help="minimum age in hours (default 24)")
    args = parser.parse_args(argv)

    if not os.environ.get(DB_PATH_ENV):
        print(f"{DB_PATH_ENV} is not set; photo cleanup needs the SQLite store. Nothing deleted.", file=sys.stderr)
        return 1
    store = get_store()
    deleted = store.delete_unreferenced_photos(timestamps.now() - timedelta(hours=args.hours))  # type: ignore[attr-defined]
    print(f"Deleted {deleted} photo(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
