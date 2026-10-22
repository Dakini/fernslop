import io

from PIL import Image

from app import photo_strip, timestamps
from app.models import StoredPhoto
from app.store import DATABASE_URL_ENV, get_store

PHOTO_ID = "00000000-0000-4000-8000-000000000001"


def make_jpeg_with_gps():
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (51.0, 30.0, 12.0)}
    out = io.BytesIO()
    Image.new("RGB", (2, 2), "green").save(out, "JPEG", exif=exif)
    return out.getvalue()


def test_strip_command_strips_stored_photos_in_place_and_a_second_run_changes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(DATABASE_URL_ENV, f"sqlite:///{tmp_path / 'fern.db'}")
    store = get_store()
    url = f"/api/photos/{PHOTO_ID}"
    store.save_photo(
        StoredPhoto(
            id=PHOTO_ID, url=url, content_type="image/jpeg", created_at=timestamps.now(), data=make_jpeg_with_gps()
        )
    )

    photo_strip.main([])
    first_output = capsys.readouterr().out.strip()
    photo_strip.main([])
    second_output = capsys.readouterr().out.strip()

    stripped = store.get_photo(PHOTO_ID)
    # The seed photo has no metadata, so only the uploaded one changes.
    assert first_output == "Stripped 1 photo(s)"
    assert second_output == "Stripped 0 photo(s)"
    assert (stripped.url, stripped.content_type) == (url, "image/jpeg")
    assert dict(Image.open(io.BytesIO(stripped.data)).getexif()) == {}
