import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.sql_store import SqlStore
from app.store import get_store

JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body"
PNG = b"\x89PNG\r\n\x1a\n" + b"png-body"
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
    [(b"GIF89a....", "image/gif"), (PNG, "image/jpeg")],
)
def test_upload_of_wrong_type_is_415_and_stores_nothing(api, store, saved, data, content_type):

    response = upload(api, data, content_type)

    assert response.status_code == 415
    assert response.json() == {"message": "Please use a JPG, PNG or WebP image"}
    assert saved == []


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


@pytest.mark.parametrize("photo_id", [MISSING_ID, "not-a-uuid"])
def test_get_of_unknown_or_non_uuid_id_is_404_not_422(api, photo_id):
    response = api.get(f"/api/photos/{photo_id}")

    assert response.status_code == 404
    assert response.json() == {"message": "Photo not found"}
