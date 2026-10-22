import pytest
from fastapi.testclient import TestClient

from app import rate_limit
from app.main import app

JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body"
ACTOR = {"X-Device-Id": "device-1", "X-Actor-Name": "Tess"}


@pytest.fixture
def limits(monkeypatch):
    """Set rate limits from ``bucket=value`` keywords and rebuild the limiter."""

    def set_limits(**values):
        for bucket, value in values.items():
            monkeypatch.setenv(rate_limit.env_name(bucket), value)
        rate_limit.reset()

    return set_limits


def from_ip(host):
    return TestClient(app, client=(host, 50000))


def create_room(api, headers=None):
    return api.post("/api/rooms", json={"name": "Garden"}, headers=headers)


def upload_photo(api):
    return api.post("/api/photos", files={"file": ("photo", JPEG, "image/jpeg")})


# --- Over the limit -------------------------------------------------------------


def test_create_room_over_the_limit_is_429_with_retry_after_and_creates_nothing(client, limits):
    limits(create_room="2/hour")
    create_room(client)
    create_room(client)
    rooms_before = len(client.get("/api/rooms").json())

    # The body is not JSON either: the limit answers before the body is read.
    response = client.post("/api/rooms", content=b"x", headers={"content-type": "text/plain"})

    assert response.status_code == 429
    retry_after = int(response.headers["retry-after"])
    assert 3500 < retry_after <= 3600
    assert response.json()["message"] == f"You're going a bit fast. Try again in {retry_after} seconds."
    assert len(client.get("/api/rooms").json()) == rooms_before


def test_photo_limit_does_not_block_other_writes_or_other_ips(client, limits):
    limits(upload_photo="1/hour")
    room = create_room(client).json()
    upload_photo(client)

    blocked = upload_photo(client)
    post = client.post(f"/api/rooms/{room['id']}/posts", json={"text": "hi"}, headers=ACTOR)
    other_ip = upload_photo(from_ip("203.0.113.9"))

    assert blocked.status_code == 429
    assert post.status_code == 201
    assert other_ip.status_code == 201


# --- Who the client is ------------------------------------------------------------


def test_limit_keys_on_the_peer_ip_or_ipv6_64_and_ignores_a_client_sent_x_forwarded_for(limits):
    # No proxy is trusted here (uvicorn's --proxy-headers is not in play), as on a local run.
    limits(create_room="1/hour")
    create_room(from_ip("2001:db8:1:2::1"), headers={"X-Forwarded-For": "198.51.100.1"})

    same_64 = create_room(from_ip("2001:db8:1:2:ffff::9"), headers={"X-Forwarded-For": "198.51.100.2"})
    other_64 = create_room(from_ip("2001:db8:1:3::1"))

    assert same_64.status_code == 429
    assert other_64.status_code == 201


# --- Never limited ------------------------------------------------------------------


def test_reads_and_health_are_never_limited_and_the_env_flag_turns_limits_off(client, limits, monkeypatch):
    limits(create_room="1/hour", write="1/minute")
    statuses = {client.get(path).status_code for path in ["/api/rooms", "/api/health"] * 5}
    create_room(client)
    monkeypatch.setenv(rate_limit.DISABLE_ENV, "off")
    rate_limit.reset()

    response = create_room(client)

    assert statuses == {200}
    assert response.status_code == 201
