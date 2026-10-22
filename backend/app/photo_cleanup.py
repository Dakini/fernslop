"""Delete uploaded photos that were never posted.

Run ``uv run python -m app.photo_cleanup [--hours N]``. It uses the configured
database (``FERNSLOP_DATABASE_URL``, see ``app/store.py``). A photo goes if it is
older than N hours (default 24) and no feed event's ``photo_url`` points at it.
"""

import argparse
import sys
from datetime import timedelta

from app import timestamps
from app.store import get_store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Delete photos older than N hours that no post uses.")
    parser.add_argument("--hours", type=float, default=24, help="minimum age in hours (default 24)")
    args = parser.parse_args(argv)

    store = get_store()
    deleted = store.delete_unreferenced_photos(timestamps.now() - timedelta(hours=args.hours))  # type: ignore[attr-defined]
    print(f"Deleted {deleted} photo(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
