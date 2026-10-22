import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import timestamps
from app.main import app
from app.models import Room
from app.store import Store, get_store

SEED_ROOM_NAMES = ["Elm Street Allotment", "Balcony Jungle", "Orchard Corner"]


@pytest.fixture
def store():
    """A fresh seeded store, injected in place of the module-level singleton."""
    fresh = Store()
    app.dependency_overrides[get_store] = lambda: fresh
    yield fresh
    app.dependency_overrides.pop(get_store, None)


@pytest.fixture
def rooms_client(store):
    return TestClient(app)


@pytest.fixture
def empty_client():
    fresh = Store(seed=False)
    app.dependency_overrides[get_store] = lambda: fresh
    yield TestClient(app), fresh
    app.dependency_overrides.pop(get_store, None)


def make_room(name="Room", *, last_activity_at, created_at=None):
    created_at = created_at or last_activity_at
    return Room(
        id=str(uuid.uuid4()),
        name=name,
        description="",
        region="",
        created_at=created_at,
        last_activity_at=last_activity_at,
    )


def seed_room_id(store, name):
    return next(room.id for room in store.list_rooms() if room.name == name)


# --- List ------------------------------------------------------------------


def test_list_rooms_on_seed_returns_three_summaries_newest_activity_first(rooms_client):
    response = rooms_client.get("/api/rooms")

    assert response.status_code == 200
    assert [summary["room"]["name"] for summary in response.json()] == SEED_ROOM_NAMES


def test_list_rooms_summary_has_room_plants_and_areas_only(rooms_client):
    summary = rooms_client.get("/api/rooms").json()[0]

    assert set(summary) == {"room", "plants", "areas"}
    assert set(summary["plants"][0]) == {"x_pct", "y_pct", "category"}
    assert set(summary["areas"][0]) >= {"id", "room_id", "label", "shape", "colour", "deleted_at"}


def test_list_rooms_summaries_hold_only_live_plants_and_areas(rooms_client, store):
    # The seed soft-deletes one Elm Street plant and one Balcony Jungle area.
    summaries = {s["room"]["name"]: s for s in rooms_client.get("/api/rooms").json()}

    assert len(summaries["Elm Street Allotment"]["plants"]) == 4
    assert len(summaries["Balcony Jungle"]["areas"]) == 1
    assert all(area["deleted_at"] is None for s in summaries.values() for area in s["areas"])


def test_list_rooms_plant_category_comes_from_the_reference_table(rooms_client, store):
    elm = seed_room_id(store, "Elm Street Allotment")
    expected = sorted(
        (rp.x_pct, rp.y_pct, store.get_plant(rp.plant_id).category) for rp in store.list_room_plants(elm)
    )

    summary = rooms_client.get("/api/rooms").json()[0]

    assert sorted((p["x_pct"], p["y_pct"], p["category"]) for p in summary["plants"]) == expected


def test_list_rooms_orders_by_last_activity_then_newest_created(empty_client):
    client, store = empty_client
    t = timestamps.now()
    store.save_room(make_room("old", last_activity_at=t - timedelta(days=2)))
    store.save_room(make_room("tie-older", last_activity_at=t, created_at=t - timedelta(days=5)))
    store.save_room(make_room("tie-newer", last_activity_at=t, created_at=t - timedelta(days=1)))

    response = client.get("/api/rooms")

    assert [s["room"]["name"] for s in response.json()] == ["tie-newer", "tie-older", "old"]


def test_list_rooms_skips_a_room_plant_whose_plant_is_missing(rooms_client, store):
    elm = seed_room_id(store, "Elm Street Allotment")
    orphan = store.list_room_plants(elm)[0].model_copy(update={"id": str(uuid.uuid4()), "plant_id": "no-such-plant"})
    store.save_room_plant(orphan)

    response = rooms_client.get("/api/rooms")

    assert response.status_code == 200
    assert len(response.json()[0]["plants"]) == 4


def test_list_rooms_with_no_rooms_returns_empty_list(empty_client):
    client, _ = empty_client

    response = client.get("/api/rooms")

    assert response.status_code == 200
    assert response.json() == []


# --- Create ----------------------------------------------------------------


def test_create_room_trims_fields_and_returns_201_room(rooms_client):
    response = rooms_client.post("/api/rooms", json={"name": "  Back Yard  ", "description": " Sunny "})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "name", "description", "region", "created_at", "last_activity_at"}
    assert body["name"] == "Back Yard"
    assert body["description"] == "Sunny"
    assert body["region"] == ""


def test_create_room_assigns_uuid4_id_and_equal_timestamps(rooms_client):
    body = rooms_client.post("/api/rooms", json={"name": "Back Yard"}).json()

    assert uuid.UUID(body["id"]).version == 4
    assert body["created_at"] == body["last_activity_at"]
    assert body["created_at"].endswith("Z")


def test_create_room_trims_region(rooms_client):
    body = rooms_client.post("/api/rooms", json={"name": "A", "region": "  Kent "}).json()

    assert body["region"] == "Kent"


def test_create_room_ignores_extra_body_fields(rooms_client):
    response = rooms_client.post(
        "/api/rooms", json={"name": "A", "id": "mine", "created_at": "2000-01-01T00:00:00.000Z", "extra": 1}
    )

    body = response.json()
    assert response.status_code == 201
    assert body["id"] != "mine"
    assert not body["created_at"].startswith("2000")
    assert "extra" not in body


def test_create_room_appears_first_in_list_with_empty_state(rooms_client):
    created = rooms_client.post("/api/rooms", json={"name": "Back Yard"}).json()

    listed = rooms_client.get("/api/rooms").json()
    state = rooms_client.get(f"/api/rooms/{created['id']}").json()

    assert listed[0]["room"] == created
    assert len(listed) == 4
    assert state["room"] == created
    assert state["plants"] == []
    assert state["areas"] == []
    assert state["feed"] == []


def test_create_two_rooms_with_the_same_name_both_succeed_with_different_ids(rooms_client):
    first = rooms_client.post("/api/rooms", json={"name": "Twin"})
    second = rooms_client.post("/api/rooms", json={"name": "Twin"})

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_create_room_works_with_missing_or_malformed_actor_headers(rooms_client):
    missing = rooms_client.post("/api/rooms", json={"name": "A"})
    malformed = rooms_client.post(
        "/api/rooms", json={"name": "B"}, headers={"X-Device-Id": "", "X-Actor-Name": "%ZZ%FF"}
    )

    assert missing.status_code == 201
    assert malformed.status_code == 201


def test_create_room_writes_no_feed_event(rooms_client, store):
    created = rooms_client.post("/api/rooms", json={"name": "A"}).json()

    assert store.list_feed_events(created["id"]) == []


def test_create_room_does_not_change_other_rooms(rooms_client, store):
    before = store.list_rooms()

    rooms_client.post("/api/rooms", json={"name": "A"})

    assert [r for r in store.list_rooms() if r in before] == before


# --- Create: validation ----------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"description": "no name"},
        {"name": None},
        {"name": 5},
        {"name": ["a"]},
        {"name": True},
        {"name": ""},
        {"name": "   "},
        {"name": "\t\n "},
    ],
)
def test_create_room_with_missing_non_string_or_blank_name_gives_400(rooms_client, store, body):
    response = rooms_client.post("/api/rooms", json=body)

    assert response.status_code == 400
    assert response.json() == {"message": "A room needs a name"}
    assert len(store.list_rooms()) == 3


@pytest.mark.parametrize(
    ("field", "limit"),
    [("name", 60), ("description", 200), ("region", 60)],
)
def test_create_room_accepts_a_field_at_its_max_length_after_trimming(rooms_client, field, limit):
    body = {"name": "n", field: "  " + "x" * limit + "  "}

    response = rooms_client.post("/api/rooms", json=body)

    assert response.status_code == 201
    assert response.json()[field] == "x" * limit


@pytest.mark.parametrize(
    ("field", "label", "limit"),
    [("name", "Name", 60), ("description", "Description", 200), ("region", "Region", 60)],
)
def test_create_room_rejects_a_field_one_over_its_max_length_without_truncating(rooms_client, store, field, label, limit):
    body = {"name": "n", field: "x" * (limit + 1)}

    response = rooms_client.post("/api/rooms", json=body)

    assert response.status_code == 400
    assert response.json() == {"message": f"{label} must be at most {limit} characters"}
    assert len(store.list_rooms()) == 3


@pytest.mark.parametrize("field", ["description", "region"])
def test_create_room_with_non_string_optional_field_gives_400(rooms_client, field):
    response = rooms_client.post("/api/rooms", json={"name": "n", field: 3})

    assert response.status_code == 400
    assert "message" in response.json()


def test_create_room_with_invalid_json_gives_400_not_422(rooms_client):
    response = rooms_client.post("/api/rooms", content=b"{not json", headers={"Content-Type": "application/json"})

    assert response.status_code == 400
    assert "message" in response.json()


def test_create_room_with_empty_body_gives_400_not_422(rooms_client):
    response = rooms_client.post("/api/rooms")

    assert response.status_code == 400


@pytest.mark.parametrize("content", [b"[]", b'"name"', b"42", b"null", b"true"])
def test_create_room_with_non_object_body_gives_400_not_422(rooms_client, content):
    response = rooms_client.post("/api/rooms", content=content, headers={"Content-Type": "application/json"})

    assert response.status_code == 400
    assert "message" in response.json()


def test_create_room_with_non_utf8_body_gives_400(rooms_client):
    response = rooms_client.post("/api/rooms", content=b"\xff\xfe", headers={"Content-Type": "application/json"})

    assert response.status_code == 400


# --- Get state -------------------------------------------------------------


def test_get_room_state_returns_room_live_plants_areas_and_feed(rooms_client, store):
    elm = seed_room_id(store, "Elm Street Allotment")

    response = rooms_client.get(f"/api/rooms/{elm}")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"room", "plants", "areas", "feed"}
    assert body["room"]["id"] == elm
    assert body["room"]["name"] == "Elm Street Allotment"
    assert len(body["plants"]) == 4
    assert len(body["areas"]) == 2
    assert all(item["deleted_at"] is None for item in body["plants"] + body["areas"])


def test_get_room_state_excludes_soft_deleted_plants_and_areas(rooms_client, store):
    balcony = seed_room_id(store, "Balcony Jungle")

    body = rooms_client.get(f"/api/rooms/{balcony}").json()

    assert len(store.list_areas(balcony, include_deleted=True)) == 2
    assert len(body["areas"]) == 1


def test_get_room_state_feed_is_full_newest_first_and_includes_undone_events(rooms_client, store):
    elm = seed_room_id(store, "Elm Street Allotment")

    feed = rooms_client.get(f"/api/rooms/{elm}").json()["feed"]

    assert len(feed) == 11
    created = [event["created_at"] for event in feed]
    assert created == sorted(created, reverse=True)
    assert [event["id"] for event in feed] == [event.id for event in store.list_feed_events(elm)]
    assert any(event["undone_at"] is not None for event in feed)


def test_get_room_state_skips_a_room_plant_whose_plant_is_missing(rooms_client, store):
    elm = seed_room_id(store, "Elm Street Allotment")
    orphan = store.list_room_plants(elm)[0].model_copy(update={"id": str(uuid.uuid4()), "plant_id": "no-such-plant"})
    store.save_room_plant(orphan)

    response = rooms_client.get(f"/api/rooms/{elm}")

    assert response.status_code == 200
    assert orphan.id not in [plant["id"] for plant in response.json()["plants"]]


@pytest.mark.parametrize("room_id", ["nope", "123", "not-a-uuid-at-all", str(uuid.uuid4()), str(uuid.uuid4()).upper()])
def test_get_room_state_for_unknown_id_gives_404_not_422(rooms_client, room_id):
    response = rooms_client.get(f"/api/rooms/{room_id}")

    assert response.status_code == 404
    assert response.json() == {"message": "Room not found"}


def test_get_room_state_needs_no_actor_headers(rooms_client, store):
    elm = seed_room_id(store, "Elm Street Allotment")

    response = rooms_client.get(f"/api/rooms/{elm}")

    assert response.status_code == 200
