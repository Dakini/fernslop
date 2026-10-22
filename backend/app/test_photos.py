import io
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin

from app.main import app
from app.sql_store import SqlStore
from app.store import get_store


def make_image(fmt, size=(2, 2), mode="RGB", **params):
    out = io.BytesIO()
    Image.new(mode, size, "green").save(out, fmt, **params)
    return out.getvalue()


def camera_exif(orientation=6):
    """EXIF as a phone writes it: orientation, camera model, date and GPS position."""
    exif = Image.Exif()
    exif[0x0112] = orientation
    exif[0x0110] = "Pixel 9"
    exif[0x0132] = "2026:05:01 09:30:00"
    exif[0x8825] = {1: "N", 2: (51.0, 30.0, 12.0)}
    return exif


def stored_image(api, photo):
    return Image.open(io.BytesIO(api.get(photo["url"]).content))


JPEG = make_image("JPEG")
PNG = make_image("PNG")
CACHE_CONTROL = "public, max-age=31536000, immutable"
MISSING_ID = "00000000-0000-4000-8000-000000000000"


@pytest.fixture
def store():
    """A fresh seeded store, injected in place of the configured store."""
    fresh = SqlStore("sqlite://")
    app.dependency_overrides[get_store] = lambda: fresh
    yield fresh
    app.dependency_overrides.pop(get_store, None)


@pytest.fixture
def api(store):
    return TestClient(app)


@pytest.fixture
def saved(store):
    """The photos passed to ``save_photo`` so far."""
    calls = []
    real = store.save_photo
    store.save_photo = lambda photo: (calls.append(photo), real(photo))[1]
    return calls


def upload(api, data=JPEG, content_type="image/jpeg", headers=None):
    return api.post("/api/photos", files={"file": ("photo", data, content_type)}, headers=headers)


# --- Upload ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "content_type"),
    [(JPEG, "image/jpeg"), (PNG, "image/png")],
)
def test_upload_of_valid_image_returns_201_with_new_uuid4_id_and_url(api, data, content_type):
    response = upload(api, data, content_type)

    body = response.json()
    assert response.status_code == 201
    assert set(body) == {"id", "url"}
    assert uuid.UUID(body["id"]).version == 4
    assert body["url"] == f"/api/photos/{body['id']}"


def test_upload_over_5_mb_is_413_and_stores_nothing(api, store, saved):

    response = upload(api, JPEG + b"\x00" * (5 * 1024 * 1024))

    assert response.status_code == 413
    assert response.json() == {"message": "That photo is over 5 MB"}
    assert saved == []


@pytest.mark.parametrize(
    ("data", "content_type"),
    [
        (b"GIF89a....", "image/gif"),
        (PNG, "image/jpeg"),
        # Passes the magic-byte check but Pillow cannot decode it (audit finding 7).
        (b"\xff\xd8\xff\xe0" + b"jpeg-body", "image/jpeg"),
    ],
)
def test_upload_of_wrong_type_is_415_and_stores_nothing(api, store, saved, data, content_type):

    response = upload(api, data, content_type)

    assert response.status_code == 415
    assert response.json() == {"message": "Please use a JPG, PNG or WebP image"}
    assert saved == []


def test_upload_over_the_decompression_bomb_pixel_limit_is_415_and_stores_nothing(api, saved, monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)

    response = upload(api, make_image("PNG", size=(4, 4)), "image/png")

    assert response.status_code == 415
    assert response.json() == {"message": "Please use a JPG, PNG or WebP image"}
    assert saved == []


# --- Metadata stripping --------------------------------------------------------


def test_upload_of_jpeg_strips_exif_xmp_and_comment_and_turns_pixels_upright(api):
    data = make_image("JPEG", size=(4, 2), exif=camera_exif(), xmp=b"<x:xmpmeta/>", comment=b"Ada's phone")

    photo = upload(api, data, "image/jpeg").json()

    image = stored_image(api, photo)
    assert image.format == "JPEG"
    assert image.size == (2, 4)  # Orientation 6 rotated into the pixels
    assert dict(image.getexif()) == {}
    assert not {"exif", "xmp", "comment"} & set(image.info)


def test_upload_of_png_and_animated_webp_strips_metadata_and_keeps_type_transparency_and_frames(api):
    text = PngImagePlugin.PngInfo()
    text.add_text("Author", "Ada")
    text.add_itxt("Comment", "kitchen window")
    png = make_image("PNG", mode="RGBA", exif=camera_exif(1), pnginfo=text)
    frames = [Image.new("RGBA", (2, 2), (255, 0, 0, 128)), Image.new("RGBA", (2, 2), "blue")]
    out = io.BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], exif=camera_exif(1), xmp=b"<x:xmpmeta/>")

    stored = [
        stored_image(api, upload(api, png, "image/png").json()),
        stored_image(api, upload(api, out.getvalue(), "image/webp").json()),
    ]

    assert [(image.format, image.mode) for image in stored] == [("PNG", "RGBA"), ("WEBP", "RGBA")]
    assert stored[1].n_frames == 2
    for image in stored:
        assert dict(image.getexif()) == {}
        assert not {"exif", "xmp", "Author", "Comment"} & set(image.info)


# --- Serving -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "content_type"),
    [(JPEG, "image/jpeg"), (PNG, "image/png")],
)
def test_get_returns_the_uploaded_bytes_with_content_type_and_cache_header(api, data, content_type):
    photo = upload(api, data, content_type).json()

    response = api.get(photo["url"])

    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == content_type
    assert response.headers["cache-control"] == CACHE_CONTROL
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"] == "inline"


@pytest.mark.parametrize("photo_id", [MISSING_ID, "not-a-uuid"])
def test_get_of_unknown_or_non_uuid_id_is_404_not_422(api, photo_id):
    response = api.get(f"/api/photos/{photo_id}")

    assert response.status_code == 404
    assert response.json() == {"message": "Photo not found"}
