from datetime import timedelta

from fastapi.testclient import TestClient

from app import photo_cleanup, timestamps
from app.main import app
from app.models import StoredPhoto
from app.store import DATABASE_URL_ENV, get_store
from app.test_store import make_event

OLD_ORPHAN = "00000000-0000-4000-8000-000000000001"
OLD_POSTED = "00000000-0000-4000-8000-000000000002"
NEW_ORPHAN = "00000000-0000-4000-8000-000000000003"


def make_photo(photo_id, age_hours):
    return StoredPhoto(
        id=photo_id,
        url=f"/api/photos/{photo_id}",
        content_type="image/png",
        created_at=timestamps.now() - timedelta(hours=age_hours),
        data=b"png",
    )


def test_cleanup_deletes_only_old_photos_no_post_uses_and_reports_the_count(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(DATABASE_URL_ENV, f"sqlite:///{tmp_path / 'fern.db'}")
    store = get_store()
    seeded_photos = {e.photo_url for room in store.list_rooms() for e in store.list_feed_events(room.id) if e.photo_url}
    for photo_id, age in [(OLD_ORPHAN, 48), (OLD_POSTED, 48), (NEW_ORPHAN, 1)]:
        store.save_photo(make_photo(photo_id, age))
    store.save_feed_event(make_event(photo_url=f"/api/photos/{OLD_POSTED}"))

    exit_code = photo_cleanup.main([])

    client = TestClient(app)
    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "Deleted 1 photo(s)"
    assert client.get(f"/api/photos/{OLD_ORPHAN}").status_code == 404
    assert client.get(f"/api/photos/{OLD_POSTED}").status_code == 200
    assert client.get(f"/api/photos/{NEW_ORPHAN}").status_code == 200
    assert all(client.get(url).status_code == 200 for url in seeded_photos)
