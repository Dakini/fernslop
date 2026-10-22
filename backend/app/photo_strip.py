"""Strip metadata from photos that were stored before uploads were stripped.

Run ``uv run python -m app.photo_strip``. It uses the configured database
(``FERNSLOP_DATABASE_URL``, see ``app/store.py``). Each photo is rewritten in place
(same id, URL and type) when it still carries metadata, and the command prints how
many changed; a photo without metadata is left as it is, so a second run changes
nothing. A stored photo Pillow cannot read is left alone and counted as skipped.
"""

import sys

from sqlalchemy import select

from app.errors import ApiError
from app.sql_store import _photos
from app.store import get_store
from app.uploads import ValidatedImage, strip_metadata


def main(argv: list[str] | None = None) -> int:
    store = get_store()
    with store._tx() as conn:  # type: ignore[attr-defined]  # listing photos is not part of StoreProtocol
        photo_ids = list(conn.execute(select(_photos.c.id).order_by(_photos.c.id)).scalars())

    changed = skipped = 0
    for photo_id in photo_ids:
        photo = store.get_photo(photo_id)
        if photo is None:  # deleted since the listing
            continue
        try:
            data = strip_metadata(ValidatedImage(data=photo.data, content_type=photo.content_type, filename=None))
        except ApiError:
            skipped += 1
            continue
        if data != photo.data:
            store.save_photo(photo.model_copy(update={"data": data}))
            changed += 1

    print(f"Stripped {changed} photo(s)" + (f", skipped {skipped} unreadable" if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
