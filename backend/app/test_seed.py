import struct
import uuid
import zlib
from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest

from app.models import (
    DeletePlantPayload,
    FeedEvent,
    RestoreAreaPayload,
    RestorePlantPayload,
    Room,
    StoredPhoto,
)
from app.seed import PNG_1X1, SeedData, build_seed, plant_id, seed_id

NOW = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)



# --- Helpers -----------------------------------------------------------------


def seed(now=NOW) -> SeedData:
    return build_seed(now)


def room_named(data: SeedData, name: str) -> Room:
    return next(room for room in data.rooms if room.name == name)


def live_plants(data: SeedData, room: Room):
    return [p for p in data.room_plants if p.room_id == room.id and p.deleted_at is None]


def live_areas(data: SeedData, room: Room):
    return [a for a in data.areas if a.room_id == room.id and a.deleted_at is None]


def common_name(data: SeedData, room_plant) -> str:
    return next(p.common_name for p in data.plants if p.id == room_plant.plant_id)


def events_of(data: SeedData, room: Room, type_: str) -> list[FeedEvent]:
    return [e for e in data.feed_events if e.room_id == room.id and e.type == type_]


def plants_by_name(data: SeedData, room: Room) -> dict:
    return {common_name(data, p): p for p in data.room_plants if p.room_id == room.id}


# --- build_seed --------------------------------------------------------------


def test_build_seed_with_a_naive_now_raises_value_error():
    with pytest.raises(ValueError):
        build_seed(datetime(2026, 10, 22, 12, 0, 0))


def test_build_seed_called_twice_with_the_same_now_gives_equal_data():
    assert build_seed(NOW) == build_seed(NOW)


def test_build_seed_ids_do_not_depend_on_now():
    later = build_seed(NOW + timedelta(days=3))

    assert [r.id for r in later.rooms] == [r.id for r in seed().rooms]
    assert [e.id for e in later.feed_events] == [e.id for e in seed().feed_events]


def test_build_seed_timestamps_move_with_now():
    later = build_seed(NOW + timedelta(days=3))

    assert later.rooms[0].created_at == seed().rooms[0].created_at + timedelta(days=3)


def test_build_seed_calls_return_independent_objects():
    first = seed()
    first.plants[0].common_name = "Mutated"
    first.rooms[0].name = "Mutated"

    second = seed()

    assert second.plants[0].common_name == "Basil"
    assert second.rooms[0].name == "Elm Street Allotment"


def test_build_seed_has_no_follows():
    assert seed().follows == []


# --- Plant reference table ---------------------------------------------------

PLANT_IDS = [
    "plant-basil",
    "plant-mint",
    "plant-rosemary",
    "plant-thyme",
    "plant-parsley",
    "plant-chives",
    "plant-coriander",
    "plant-sage",
    "plant-lavender",
    "plant-oregano",
    "plant-tomato",
    "plant-courgette",
    "plant-runner-bean",
    "plant-lettuce",
    "plant-carrot",
    "plant-potato",
    "plant-onion",
    "plant-garlic",
    "plant-spinach",
    "plant-kale",
    "plant-pea",
    "plant-beetroot",
    "plant-radish",
    "plant-chilli-pepper",
    "plant-strawberry",
    "plant-cucumber",
    "plant-rose",
    "plant-dahlia",
    "plant-sunflower",
    "plant-tulip",
    "plant-daffodil",
    "plant-marigold",
    "plant-sweet-pea",
    "plant-geranium",
    "plant-foxglove",
    "plant-hydrangea",
    "plant-nasturtium",
    "plant-cosmos",
    "plant-peony",
    "plant-monstera",
    "plant-snake-plant",
    "plant-pothos",
    "plant-peace-lily",
    "plant-spider-plant",
    "plant-fiddle-leaf-fig",
    "plant-aloe-vera",
    "plant-boxwood",
    "plant-blueberry",
    "plant-apple-tree",
    "plant-olive-tree",
    "plant-japanese-maple",
]


def test_plant_table_has_51_plants():
    assert len(seed().plants) == 51


def test_plant_table_ids_match_the_frontends_in_order():
    assert [p.id for p in seed().plants] == PLANT_IDS


@pytest.mark.parametrize(
    "pid",
    ["plant-tomato", "plant-chilli-pepper", "plant-fiddle-leaf-fig", "plant-japanese-maple", "plant-runner-bean"],
)
def test_plant_table_contains_the_spot_checked_ids(pid):
    assert pid in {p.id for p in seed().plants}


def test_plant_table_ids_are_unique():
    ids = [p.id for p in seed().plants]

    assert len(set(ids)) == len(ids)


def test_plant_table_category_counts_match_the_frontend():
    counts = Counter(p.category for p in seed().plants)

    assert counts == {"herb": 10, "vegetable": 16, "flower": 13, "houseplant": 7, "shrub": 2, "tree": 3}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Tomato", "plant-tomato"),
        ("Chilli Pepper", "plant-chilli-pepper"),
        ("Fiddle Leaf Fig", "plant-fiddle-leaf-fig"),
        ("  Odd -- Name! ", "plant-odd-name"),
    ],
)
def test_plant_id_slugs_the_common_name(name, expected):
    assert plant_id(name) == expected


def test_plant_table_every_row_has_the_same_source_and_no_image():
    for plant in seed().plants:
        assert plant.image_url is None
        assert plant.source == "RHS Grow Your Own (general guidance)"
        assert plant.source_url == "https://www.rhs.org.uk/"


def test_plant_table_tomato_row_matches_the_frontend():
    tomato = next(p for p in seed().plants if p.id == "plant-tomato")

    assert tomato.model_dump() == {
        "id": "plant-tomato",
        "common_name": "Tomato",
        "scientific_name": "Solanum lycopersicum",
        "category": "vegetable",
        "description": "Heavy-feeding summer fruiting crop.",
        "image_url": None,
        "water_every_days": 2,
        "feed_every_days": 10,
        "prune_every_days": 7,
        "harvest_every_days": 3,
        "source": "RHS Grow Your Own (general guidance)",
        "source_url": "https://www.rhs.org.uk/",
    }


def test_plant_table_keeps_null_intervals_as_none_not_zero():
    coriander = next(p for p in seed().plants if p.id == "plant-coriander")
    aloe = next(p for p in seed().plants if p.id == "plant-aloe-vera")

    assert (coriander.feed_every_days, coriander.prune_every_days) == (None, None)
    assert (aloe.feed_every_days, aloe.prune_every_days, aloe.harvest_every_days) == (None, None, None)
    assert aloe.water_every_days == 21


def test_plant_table_keeps_special_characters_in_text():
    plants = {p.id: p for p in seed().plants}

    assert plants["plant-strawberry"].scientific_name == "Fragaria × ananassa"
    assert plants["plant-sweet-pea"].description == "Scented climber — pick often for more."


def test_plant_table_intervals_are_positive_or_none():
    for plant in seed().plants:
        for value in (plant.water_every_days, plant.feed_every_days, plant.prune_every_days, plant.harvest_every_days):
            assert value is None or value > 0


# --- Demo rooms --------------------------------------------------------------


def test_seed_has_exactly_three_rooms_with_uuid_ids():
    data = seed()

    assert [r.name for r in data.rooms] == ["Elm Street Allotment", "Balcony Jungle", "Orchard Corner"]
    for room in data.rooms:
        assert str(uuid.UUID(room.id)) == room.id


def test_seed_room_ids_are_derived_from_the_namespace_and_a_readable_key():
    ids = [r.id for r in seed().rooms]

    assert ids == [seed_id("room:elm-street"), seed_id("room:balcony-jungle"), seed_id("room:orchard-corner")]


def test_room_a_has_its_name_description_and_region():
    room = room_named(seed(), "Elm Street Allotment")

    assert room.description == "Plot 14 — shared by the whole street."
    assert room.region == "Bristol, UK"


def test_room_a_has_the_veg_bed_and_pond_areas():
    data = seed()
    areas = {a.label: a for a in live_areas(data, room_named(data, "Elm Street Allotment"))}

    assert set(areas) == {"Veg bed", "Pond"}
    veg, pond = areas["Veg bed"], areas["Pond"]
    assert (veg.shape, veg.x_pct, veg.y_pct, veg.w_pct, veg.h_pct, veg.colour) == ("rect", 8, 12, 40, 45, "soil")
    assert (pond.shape, pond.x_pct, pond.y_pct, pond.w_pct, pond.h_pct, pond.colour) == (
        "ellipse",
        62,
        55,
        26,
        30,
        "water",
    )


def test_room_a_live_plants_are_at_the_specified_positions():
    data = seed()
    room = room_named(data, "Elm Street Allotment")

    positions = {common_name(data, p): (p.x_pct, p.y_pct) for p in live_plants(data, room)}

    assert positions == {"Tomato": (18, 25), "Courgette": (36, 40), "Basil": (22, 46), "Sunflower": (70, 22)}


def test_room_a_has_one_soft_deleted_lettuce():
    data = seed()
    room = room_named(data, "Elm Street Allotment")

    deleted = [p for p in data.room_plants if p.room_id == room.id and p.deleted_at is not None]

    assert [(common_name(data, p), p.x_pct, p.y_pct) for p in deleted] == [("Lettuce", 30, 35)]


def test_room_b_has_its_details_and_live_plants():
    data = seed()
    room = room_named(data, "Balcony Jungle")

    positions = {common_name(data, p): (p.x_pct, p.y_pct) for p in live_plants(data, room)}

    assert (room.description, room.region) == ("Third-floor balcony, south facing.", "Leeds, UK")
    assert positions == {"Monstera": (30, 50), "Chilli Pepper": (60, 40), "Geranium": (75, 65)}


def test_room_b_has_a_live_sunny_corner_and_a_soft_deleted_old_planter():
    data = seed()
    room = room_named(data, "Balcony Jungle")

    live = live_areas(data, room)
    deleted = [a for a in data.areas if a.room_id == room.id and a.deleted_at is not None]

    assert [(a.label, a.shape, a.colour) for a in live] == [("Sunny corner", "rect", "sage")]
    assert [(a.label, a.colour) for a in deleted] == [("Old planter", "clay")]


def test_room_c_has_empty_strings_not_none_for_description_and_region():
    room = room_named(seed(), "Orchard Corner")

    assert room.description == ""
    assert room.region == ""


def test_room_c_has_three_plants_at_distinct_positions_and_an_area():
    data = seed()
    room = room_named(data, "Orchard Corner")

    plants = live_plants(data, room)

    assert {common_name(data, p) for p in plants} == {"Apple Tree", "Blueberry", "Japanese Maple"}
    assert len({(p.x_pct, p.y_pct) for p in plants}) == len(plants)
    assert len(live_areas(data, room)) >= 1


def test_seed_plants_have_added_by_name_and_no_nickname():
    for plant in seed().room_plants:
        assert plant.added_by_name
        assert plant.nickname is None


def test_seed_only_the_lettuce_is_soft_deleted():
    data = seed()

    deleted = [common_name(data, p) for p in data.room_plants if p.deleted_at is not None]

    assert deleted == ["Lettuce"]


def test_seed_only_room_a_tomato_has_been_cared_for():
    data = seed()
    tomato = plants_by_name(data, room_named(data, "Elm Street Allotment"))["Tomato"]
    others = [p for p in data.room_plants if p is not tomato]

    assert tomato.last_watered_at is not None
    assert (tomato.last_fed_at, tomato.last_pruned_at, tomato.last_harvested_at) == (None, None, None)
    for plant in others:
        assert (plant.last_watered_at, plant.last_fed_at, plant.last_pruned_at, plant.last_harvested_at) == (
            None,
            None,
            None,
            None,
        )


# --- Bounds ------------------------------------------------------------------


def test_seed_percentages_are_within_0_to_100_and_areas_fit_the_canvas():
    data = seed()

    for plant in data.room_plants:
        assert 0 <= plant.x_pct <= 100
        assert 0 <= plant.y_pct <= 100
    for area in data.areas:
        for value in (area.x_pct, area.y_pct, area.w_pct, area.h_pct):
            assert 0 <= value <= 100
        assert area.x_pct + area.w_pct <= 100
        assert area.y_pct + area.h_pct <= 100


def test_seed_rooms_stay_within_the_limits():
    data = seed()

    for room in data.rooms:
        assert len(live_plants(data, room)) <= 50
        assert len(live_areas(data, room)) <= 10
        assert len(room.name) <= 60
        assert len(room.description) <= 200
        assert len(room.region) <= 60


# --- Timestamps --------------------------------------------------------------


def test_seed_rooms_have_different_last_activity_values():
    data = seed()

    assert len({r.last_activity_at for r in data.rooms}) == 3


def test_seed_last_activity_equals_the_newest_event_in_each_room():
    data = seed()

    for room in data.rooms:
        newest = max(e.created_at for e in data.feed_events if e.room_id == room.id)
        assert room.last_activity_at == newest


def test_seed_has_no_timestamp_later_than_now():
    data = seed()
    stamps = []
    for room in data.rooms:
        stamps += [room.created_at, room.last_activity_at]
    for plant in data.room_plants:
        stamps += [plant.created_at, plant.last_watered_at, plant.deleted_at]
    for area in data.areas:
        stamps += [area.deleted_at]
    for event in data.feed_events:
        stamps += [event.created_at, event.undone_at]
    stamps += [photo.created_at for photo in data.photos]

    assert all(stamp <= NOW for stamp in stamps if stamp is not None)


def test_seed_rooms_are_created_no_later_than_anything_in_them():
    data = seed()
    rooms = {r.id: r for r in data.rooms}

    for plant in data.room_plants:
        assert rooms[plant.room_id].created_at <= plant.created_at
    for event in data.feed_events:
        assert rooms[event.room_id].created_at <= event.created_at


def test_seed_timestamps_dump_in_the_api_format():
    room = seed().rooms[0]

    dumped = room.model_dump(mode="json")

    assert dumped["created_at"].endswith("Z")
    assert len(dumped["created_at"]) == len("2026-10-22T09:30:00.000Z")
    assert dumped["created_at"] == (NOW - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# --- Feed events -------------------------------------------------------------


def test_seed_every_room_plant_has_a_plant_added_event_with_a_delete_payload():
    data = seed()

    for plant in data.room_plants:
        added = [e for e in data.feed_events if e.type == "plant_added" and e.room_plant_id == plant.id]
        assert len(added) == 1
        assert added[0].text == f"added a {common_name(data, plant)}"
        assert added[0].undo_payload == DeletePlantPayload(kind="delete_plant", room_plant_id=plant.id)


def test_seed_every_area_has_an_area_changed_event_with_a_null_area_payload():
    data = seed()

    for area in data.areas:
        payloads = [
            e.undo_payload
            for e in data.feed_events
            if e.type == "area_changed"
            and isinstance(e.undo_payload, RestoreAreaPayload)
            and e.undo_payload.area_id == area.id
        ]
        assert len(payloads) == 1
        assert payloads[0].area is None


def test_room_a_care_done_event_matches_the_tomatos_last_watered_at():
    data = seed()
    room = room_named(data, "Elm Street Allotment")
    tomato = plants_by_name(data, room)["Tomato"]

    (event,) = events_of(data, room, "care_done")

    assert event.text == "watered the Tomato"
    assert event.room_plant_id == tomato.id
    assert event.created_at == tomato.last_watered_at
    assert isinstance(event.undo_payload, RestorePlantPayload)
    assert event.undo_payload.room_plant.id == tomato.id
    assert event.undo_payload.room_plant.last_watered_at is None


def test_room_a_plant_moved_event_is_already_undone_with_the_current_position_in_its_snapshot():
    data = seed()
    room = room_named(data, "Elm Street Allotment")
    tomato = plants_by_name(data, room)["Tomato"]

    (event,) = events_of(data, room, "plant_moved")

    assert event.room_plant_id == tomato.id
    assert event.undone_at is not None
    assert isinstance(event.undo_payload, RestorePlantPayload)
    snapshot = event.undo_payload.room_plant
    assert (snapshot.x_pct, snapshot.y_pct) == (tomato.x_pct, tomato.y_pct)


def test_room_a_plant_removed_event_is_not_undone_and_restores_the_lettuce():
    data = seed()
    room = room_named(data, "Elm Street Allotment")
    lettuce = plants_by_name(data, room)["Lettuce"]

    (event,) = events_of(data, room, "plant_removed")

    assert event.room_plant_id == lettuce.id
    assert event.undone_at is None
    assert isinstance(event.undo_payload, RestorePlantPayload)
    assert event.undo_payload.room_plant.id == lettuce.id
    assert event.undo_payload.room_plant.deleted_at is None


def test_room_a_post_has_text_no_undo_payload_and_points_at_the_seeded_photo():
    data = seed()
    room = room_named(data, "Elm Street Allotment")

    (post,) = events_of(data, room, "post")

    assert post.text
    assert post.undo_payload is None
    assert post.photo_url == f"/api/photos/{data.photos[0].id}"


def test_room_b_post_has_text_and_no_photo():
    data = seed()
    room = room_named(data, "Balcony Jungle")

    (post,) = events_of(data, room, "post")

    assert post.text
    assert post.photo_url is None
    assert post.undo_payload is None


def test_seed_covers_all_six_event_types_an_undone_event_and_a_soft_deleted_plant():
    data = seed()

    assert {e.type for e in data.feed_events} == {
        "plant_added",
        "plant_removed",
        "plant_moved",
        "care_done",
        "area_changed",
        "post",
    }
    assert any(e.undone_at is not None for e in data.feed_events)
    assert any(p.deleted_at is not None for p in data.room_plants)


def test_seed_actor_names_and_device_ids_are_valid_and_few():
    data = seed()

    for event in data.feed_events:
        assert 0 < len(event.actor_name) <= 40
        assert event.device_id
    people = {(e.actor_name, e.device_id) for e in data.feed_events}
    assert 2 <= len(people) <= 3
    assert len({device for _, device in people}) == len(people)


# --- Referential integrity ---------------------------------------------------


def test_seed_ids_are_unique_within_each_collection():
    data = seed()

    for collection in (data.rooms, data.room_plants, data.areas, data.feed_events, data.photos):
        ids = [item.id for item in collection]
        assert len(set(ids)) == len(ids)


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


def test_seed_has_one_photo_with_a_png_signature():
    (photo,) = seed().photos

    assert isinstance(photo, StoredPhoto)
    assert photo.content_type == "image/png"
    assert photo.url == f"/api/photos/{photo.id}"
    assert photo.data.startswith(b"\x89PNG\r\n\x1a\n")


def test_seed_photo_is_a_valid_1x1_png():
    data = seed().photos[0].data

    assert data == PNG_1X1
    position, chunks = 8, []
    while position < len(data):
        length, kind = struct.unpack(">I4s", data[position : position + 8])
        body = data[position + 8 : position + 8 + length]
        (crc,) = struct.unpack(">I", data[position + 8 + length : position + 12 + length])
        assert crc == zlib.crc32(kind + body)
        chunks.append((kind, body))
        position += 12 + length
    assert chunks[0][0] == b"IHDR"
    assert struct.unpack(">II", chunks[0][1][:8]) == (1, 1)
    assert chunks[-1][0] == b"IEND"
