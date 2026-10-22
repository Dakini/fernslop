import uuid
from datetime import UTC, datetime

import pytest

from app.models import DeletePlantPayload, RestoreAreaPayload, RestorePlantPayload
from app.seed import SeedData, build_seed

NOW = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)


# --- Helpers -----------------------------------------------------------------


def seed(now=NOW) -> SeedData:
    return build_seed(now)


def common_name(data: SeedData, room_plant) -> str:
    return next(p.common_name for p in data.plants if p.id == room_plant.plant_id)


# --- build_seed --------------------------------------------------------------


def test_build_seed_with_a_naive_now_raises_value_error():
    with pytest.raises(ValueError):
        build_seed(datetime(2026, 10, 22, 12, 0, 0))


def test_build_seed_called_twice_with_the_same_now_gives_equal_data():
    assert build_seed(NOW) == build_seed(NOW)


# --- Plant reference table ---------------------------------------------------


def test_plant_table_has_51_plants():
    assert len(seed().plants) == 51


# --- Demo rooms --------------------------------------------------------------


def test_seed_has_exactly_three_rooms_with_uuid_ids():
    data = seed()

    assert [r.name for r in data.rooms] == ["Elm Street Allotment", "Balcony Jungle", "Orchard Corner"]
    for room in data.rooms:
        assert str(uuid.UUID(room.id)) == room.id


# --- Bounds ------------------------------------------------------------------


# --- Timestamps --------------------------------------------------------------


# --- Feed events -------------------------------------------------------------


# --- Referential integrity ---------------------------------------------------


def test_seed_references_all_point_at_seeded_records():
    data = seed()
    room_ids = {r.id for r in data.rooms}
    plant_ids = {p.id for p in data.plants}
    room_plant_ids = {p.id for p in data.room_plants}
    area_ids = {a.id for a in data.areas}
    photo_urls = {p.url for p in data.photos}

    for plant in data.room_plants:
        assert plant.room_id in room_ids
        assert plant.plant_id in plant_ids
    for area in data.areas:
        assert area.room_id in room_ids
    for event in data.feed_events:
        assert event.room_id in room_ids
        assert event.room_plant_id is None or event.room_plant_id in room_plant_ids
        if event.photo_url is not None:
            assert event.photo_url in photo_urls
        payload = event.undo_payload
        if isinstance(payload, RestorePlantPayload):
            assert payload.room_plant.id in room_plant_ids
            assert payload.room_plant.plant_id in plant_ids
            assert payload.room_plant.room_id == event.room_id
        elif isinstance(payload, DeletePlantPayload):
            assert payload.room_plant_id in room_plant_ids
        elif isinstance(payload, RestoreAreaPayload):
            assert payload.area_id in area_ids


# --- Photo -------------------------------------------------------------------


