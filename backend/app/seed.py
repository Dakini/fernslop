"""Seed data: the plant reference table and three demo rooms.

``build_seed(now)`` returns everything as plain data. Plant ids are the
frontend's (``plant-tomato``). Every other id is a UUID derived with
``uuid.uuid5`` from ``SEED_NAMESPACE`` plus a readable key, so ids are the same
after every reset and every restart and demo room URLs stay bookmarkable.
Timestamps are computed relative to ``now`` so care timers look live.
"""

import base64
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.models import (
    DeletePlantPayload,
    FeedEvent,
    Plant,
    RestoreAreaPayload,
    RestorePlantPayload,
    Room,
    RoomArea,
    RoomPlant,
    StoredFollow,
    StoredPhoto,
)

SEED_NAMESPACE = uuid.UUID("5e3d1c0a-7b1f-4c55-9a4e-2f6a8d9b0c11")

PLANT_SOURCE = "RHS Grow Your Own (general guidance)"
PLANT_SOURCE_URL = "https://www.rhs.org.uk/"

# A valid 1x1 PNG.
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

# (common name, scientific name, category, water, feed, prune, harvest, description),
# in the order of frontend/src/services/mock/plants-seed.ts.
_PLANT_ROWS = (
    ("Basil", "Ocimum basilicum", "herb", 2, 14, 10, 7, "Fragrant annual herb that loves warmth and sun."),
    ("Mint", "Mentha spicata", "herb", 3, 28, 14, 7, "Vigorous spreading herb, best kept in a pot."),
    ("Rosemary", "Salvia rosmarinus", "herb", 10, 60, 90, 14, "Woody, drought-tolerant Mediterranean herb."),
    ("Thyme", "Thymus vulgaris", "herb", 10, 60, 60, 14, "Low, aromatic herb that likes poor, dry soil."),
    ("Parsley", "Petroselinum crispum", "herb", 3, 21, None, 7, "Leafy biennial herb for cool seasons."),
    ("Chives", "Allium schoenoprasum", "herb", 4, 30, 30, 7, "Hardy perennial with mild onion flavour."),
    ("Coriander", "Coriandrum sativum", "herb", 3, None, None, 7, "Quick annual herb that bolts in heat."),
    ("Sage", "Salvia officinalis", "herb", 10, 60, 90, 14, "Silvery-leaved perennial herb."),
    ("Lavender", "Lavandula angustifolia", "herb", 14, None, 180, None, "Scented shrub loved by bees."),
    ("Oregano", "Origanum vulgare", "herb", 7, 60, 60, 14, "Spreading perennial herb."),
    ("Tomato", "Solanum lycopersicum", "vegetable", 2, 10, 7, 3, "Heavy-feeding summer fruiting crop."),
    ("Courgette", "Cucurbita pepo", "vegetable", 2, 14, None, 3, "Prolific summer squash."),
    ("Runner Bean", "Phaseolus coccineus", "vegetable", 2, 21, None, 3, "Climbing bean with scarlet flowers."),
    ("Lettuce", "Lactuca sativa", "vegetable", 2, None, None, 5, "Fast leafy crop for cut-and-come-again."),
    ("Carrot", "Daucus carota", "vegetable", 4, None, None, None, "Root crop for light, stone-free soil."),
    ("Potato", "Solanum tuberosum", "vegetable", 5, 30, None, None, "Staple tuber, earth up as it grows."),
    ("Onion", "Allium cepa", "vegetable", 7, 30, None, None, "Easy bulb crop from sets."),
    ("Garlic", "Allium sativum", "vegetable", 10, 45, None, None, "Plant cloves in autumn for summer bulbs."),
    ("Spinach", "Spinacia oleracea", "vegetable", 3, 21, None, 5, "Cool-season leafy green."),
    ("Kale", "Brassica oleracea var. sabellica", "vegetable", 4, 30, None, 7, "Hardy brassica for winter greens."),
    ("Pea", "Pisum sativum", "vegetable", 3, None, None, 3, "Sweet climbing pod crop."),
    ("Beetroot", "Beta vulgaris", "vegetable", 4, None, None, None, "Colourful root and leaf crop."),
    ("Radish", "Raphanus sativus", "vegetable", 2, None, None, None, "Ready in about four weeks."),
    ("Chilli Pepper", "Capsicum annuum", "vegetable", 3, 14, None, 7, "Warmth-loving fruiting plant."),
    ("Strawberry", "Fragaria × ananassa", "vegetable", 2, 14, 30, 3, "Sweet summer fruit for beds or pots."),
    ("Cucumber", "Cucumis sativus", "vegetable", 2, 14, 14, 3, "Thirsty climbing fruit for greenhouse or patio."),
    ("Rose", "Rosa", "flower", 4, 21, 120, None, "Classic shrub with scented blooms."),
    ("Dahlia", "Dahlia pinnata", "flower", 3, 14, 7, None, "Showy late-summer tuberous flower."),
    ("Sunflower", "Helianthus annuus", "flower", 3, 21, None, None, "Tall cheerful annual that tracks the sun."),
    ("Tulip", "Tulipa", "flower", 7, None, None, None, "Spring bulb in every colour."),
    ("Daffodil", "Narcissus", "flower", 7, None, None, None, "Early spring bulb, very hardy."),
    ("Marigold", "Tagetes", "flower", 3, None, 7, None, "Bright annual, great companion plant."),
    ("Sweet Pea", "Lathyrus odoratus", "flower", 2, 14, 3, None, "Scented climber — pick often for more."),
    ("Geranium", "Pelargonium", "flower", 4, 14, 14, None, "Long-flowering patio favourite."),
    ("Foxglove", "Digitalis purpurea", "flower", 5, None, None, None, "Tall biennial loved by bumblebees."),
    ("Hydrangea", "Hydrangea macrophylla", "flower", 3, 30, 180, None, "Shrub with big mophead blooms."),
    ("Nasturtium", "Tropaeolum majus", "flower", 4, None, None, 7, "Edible flowers, thrives on neglect."),
    ("Cosmos", "Cosmos bipinnatus", "flower", 4, None, 7, None, "Airy annual for cutting."),
    ("Peony", "Paeonia lactiflora", "flower", 7, 60, None, None, "Long-lived perennial with lush blooms."),
    ("Monstera", "Monstera deliciosa", "houseplant", 7, 30, None, None, "Swiss cheese plant with split leaves."),
    ("Snake Plant", "Dracaena trifasciata", "houseplant", 21, 60, None, None, "Near-indestructible upright leaves."),
    ("Pothos", "Epipremnum aureum", "houseplant", 7, 30, 60, None, "Trailing vine, very forgiving."),
    ("Peace Lily", "Spathiphyllum wallisii", "houseplant", 5, 30, None, None, "Droops dramatically when thirsty."),
    ("Spider Plant", "Chlorophytum comosum", "houseplant", 7, 30, None, None, "Produces little plantlets on runners."),
    ("Fiddle Leaf Fig", "Ficus lyrata", "houseplant", 10, 30, 90, None, "Big glossy leaves, likes consistency."),
    ("Aloe Vera", "Aloe vera", "houseplant", 21, None, None, None, "Succulent with soothing gel."),
    ("Boxwood", "Buxus sempervirens", "shrub", 7, 60, 90, None, "Evergreen for hedges and topiary."),
    ("Blueberry", "Vaccinium corymbosum", "shrub", 3, 30, 365, 5, "Fruiting shrub that needs acidic soil."),
    ("Apple Tree", "Malus domestica", "tree", 10, 90, 365, 7, "Fruit tree — prune in winter."),
    ("Olive Tree", "Olea europaea", "tree", 14, 60, 365, None, "Silvery evergreen for sunny patios."),
    ("Japanese Maple", "Acer palmatum", "tree", 7, None, 365, None, "Graceful small tree with fine leaves."),
)


def plant_id(common_name: str) -> str:
    """The frontend's slug rule: ``Chilli Pepper`` becomes ``plant-chilli-pepper``."""
    return "plant-" + re.sub(r"[^a-z0-9]+", "-", common_name.lower()).strip("-")


def _build_plants() -> tuple[Plant, ...]:
    return tuple(
        Plant(
            id=plant_id(common),
            common_name=common,
            scientific_name=scientific,
            category=category,
            description=description,
            image_url=None,
            water_every_days=water,
            feed_every_days=feed,
            prune_every_days=prune,
            harvest_every_days=harvest,
            source=PLANT_SOURCE,
            source_url=PLANT_SOURCE_URL,
        )
        for common, scientific, category, water, feed, prune, harvest, description in _PLANT_ROWS
    )


_PLANTS = _build_plants()
"""The reference table, built once and reused by every ``build_seed`` call."""

_PLANT_NAMES = {plant.id: plant.common_name for plant in _PLANTS}


@dataclass
class SeedData:
    """The full seed as plain data."""

    plants: list[Plant] = field(default_factory=list)
    rooms: list[Room] = field(default_factory=list)
    room_plants: list[RoomPlant] = field(default_factory=list)
    areas: list[RoomArea] = field(default_factory=list)
    feed_events: list[FeedEvent] = field(default_factory=list)
    photos: list[StoredPhoto] = field(default_factory=list)
    follows: list[StoredFollow] = field(default_factory=list)


def seed_id(key: str) -> str:
    """A stable UUID string for a readable key such as ``room:elm-street``."""
    return str(uuid.uuid5(SEED_NAMESPACE, key))


# Demo people: (name, device id).
ADA = ("Ada", "seed-device-ada")
BEN = ("Ben", "seed-device-ben")
CLEO = ("Cleo", "seed-device-cleo")


class _Builder:
    """Accumulates the seed for one ``now``."""

    def __init__(self, now: datetime) -> None:
        self.now = now
        self.data = SeedData(plants=[plant.model_copy() for plant in _PLANTS])

    def ago(self, **kwargs: float) -> datetime:
        return self.now - timedelta(**kwargs)

    def room(self, slug: str, name: str, description: str, region: str, created_at: datetime) -> Room:
        room = Room(
            id=seed_id(f"room:{slug}"),
            name=name,
            description=description,
            region=region,
            created_at=created_at,
            last_activity_at=created_at,
        )
        self.data.rooms.append(room)
        return room

    def event(
        self,
        room: Room,
        key: str,
        type_: str,
        who: tuple[str, str],
        text: str,
        at: datetime,
        *,
        room_plant_id: str | None = None,
        photo_url: str | None = None,
        undo_payload=None,
        undone_at: datetime | None = None,
    ) -> FeedEvent:
        event = FeedEvent(
            id=seed_id(f"event:{room.id}:{key}"),
            room_id=room.id,
            type=type_,
            actor_name=who[0],
            device_id=who[1],
            room_plant_id=room_plant_id,
            text=text,
            photo_url=photo_url,
            undo_payload=undo_payload,
            undone_at=undone_at,
            created_at=at,
        )
        self.data.feed_events.append(event)
        room.last_activity_at = max(room.last_activity_at, at)
        return event

    def plant(
        self,
        room: Room,
        slug: str,
        common_name: str,
        x: float,
        y: float,
        who: tuple[str, str],
        added_at: datetime,
        *,
        deleted_at: datetime | None = None,
    ) -> RoomPlant:
        """Add a room plant and its ``plant_added`` event."""
        room_plant = RoomPlant(
            id=seed_id(f"room-plant:{room.id}:{slug}"),
            room_id=room.id,
            plant_id=plant_id(common_name),
            nickname=None,
            x_pct=x,
            y_pct=y,
            last_watered_at=None,
            last_fed_at=None,
            last_pruned_at=None,
            last_harvested_at=None,
            added_by_name=who[0],
            created_at=added_at,
            deleted_at=deleted_at,
        )
        self.data.room_plants.append(room_plant)
        self.event(
            room,
            f"added:{slug}",
            "plant_added",
            who,
            f"added a {common_name}",
            added_at,
            room_plant_id=room_plant.id,
            undo_payload=DeletePlantPayload(kind="delete_plant", room_plant_id=room_plant.id),
        )
        return room_plant

    def area(
        self,
        room: Room,
        slug: str,
        label: str,
        shape: str,
        box: tuple[float, float, float, float],
        colour: str,
        who: tuple[str, str],
        added_at: datetime,
        *,
        deleted_at: datetime | None = None,
    ) -> RoomArea:
        """Add an area and its ``area_changed`` event."""
        x, y, w, h = box
        area = RoomArea(
            id=seed_id(f"area:{room.id}:{slug}"),
            room_id=room.id,
            label=label,
            shape=shape,
            x_pct=x,
            y_pct=y,
            w_pct=w,
            h_pct=h,
            colour=colour,
            deleted_at=deleted_at,
        )
        self.data.areas.append(area)
        self.event(
            room,
            f"area:{slug}",
            "area_changed",
            who,
            f'added the area "{label}"',
            added_at,
            undo_payload=RestoreAreaPayload(kind="restore_area", area=None, area_id=area.id),
        )
        return area

    def build_elm_street(self) -> None:
        room = self.room(
            "elm-street",
            "Elm Street Allotment",
            "Plot 14 — shared by the whole street.",
            "Bristol, UK",
            self.ago(days=30),
        )
        self.area(room, "veg-bed", "Veg bed", "rect", (8, 12, 40, 45), "soil", ADA, self.ago(days=29))
        self.area(room, "pond", "Pond", "ellipse", (62, 55, 26, 30), "water", ADA, self.ago(days=29, hours=-1))

        tomato = self.plant(room, "tomato", "Tomato", 18, 25, ADA, self.ago(days=28))
        self.plant(room, "courgette", "Courgette", 36, 40, BEN, self.ago(days=27))
        self.plant(room, "basil", "Basil", 22, 46, BEN, self.ago(days=26))
        self.plant(room, "sunflower", "Sunflower", 70, 22, CLEO, self.ago(days=25))
        lettuce = self.plant(
            room, "lettuce", "Lettuce", 30, 35, CLEO, self.ago(days=24), deleted_at=self.ago(days=20)
        )

        # Lettuce was removed and can still be restored.
        self.event(
            room,
            "removed:lettuce",
            "plant_removed",
            CLEO,
            "removed a Lettuce",
            self.ago(days=20),
            room_plant_id=lettuce.id,
            undo_payload=RestorePlantPayload(
                kind="restore_plant", room_plant=lettuce.model_copy(update={"deleted_at": None})
            ),
        )

        # Tomato was moved, then the move was undone, so it is back where it is now.
        self.event(
            room,
            "moved:tomato",
            "plant_moved",
            BEN,
            "moved the Tomato",
            self.ago(days=10),
            room_plant_id=tomato.id,
            undo_payload=RestorePlantPayload(kind="restore_plant", room_plant=tomato.model_copy()),
            undone_at=self.ago(days=10, minutes=-5),
        )

        # Tomato was watered two days ago.
        watered_at = self.ago(days=2)
        before_watering = tomato.model_copy()
        tomato.last_watered_at = watered_at
        self.event(
            room,
            "watered:tomato",
            "care_done",
            ADA,
            "watered the Tomato",
            watered_at,
            room_plant_id=tomato.id,
            undo_payload=RestorePlantPayload(kind="restore_plant", room_plant=before_watering),
        )

        photo_id = seed_id("photo:elm-street-harvest")
        photo = StoredPhoto(
            id=photo_id,
            url=f"/api/photos/{photo_id}",
            content_type="image/png",
            created_at=self.ago(hours=2),
            data=PNG_1X1,
        )
        self.data.photos.append(photo)
        self.event(
            room,
            "post:harvest",
            "post",
            ADA,
            "First tomatoes of the year!",
            self.ago(hours=2),
            photo_url=photo.url,
        )

    def build_balcony(self) -> None:
        room = self.room(
            "balcony-jungle",
            "Balcony Jungle",
            "Third-floor balcony, south facing.",
            "Leeds, UK",
            self.ago(days=14),
        )
        self.area(room, "sunny-corner", "Sunny corner", "rect", (5, 60, 30, 35), "sage", BEN, self.ago(days=13))
        self.area(
            room,
            "old-planter",
            "Old planter",
            "rect",
            (60, 10, 20, 20),
            "clay",
            BEN,
            self.ago(days=13, hours=-1),
            deleted_at=self.ago(days=9),
        )
        self.plant(room, "monstera", "Monstera", 30, 50, BEN, self.ago(days=12))
        self.plant(room, "chilli-pepper", "Chilli Pepper", 60, 40, CLEO, self.ago(days=11))
        self.plant(room, "geranium", "Geranium", 75, 65, CLEO, self.ago(days=10))
        self.event(room, "post:sun", "post", BEN, "The chilli is finally flowering.", self.ago(days=1))

    def build_orchard(self) -> None:
        room = self.room("orchard-corner", "Orchard Corner", "", "", self.ago(days=6))
        self.area(room, "lawn", "Orchard lawn", "rect", (10, 10, 80, 30), "sage", CLEO, self.ago(days=5, hours=-1))
        self.plant(room, "apple-tree", "Apple Tree", 30, 40, CLEO, self.ago(days=5))
        self.plant(room, "blueberry", "Blueberry", 60, 55, ADA, self.ago(days=4, hours=12))
        self.plant(room, "japanese-maple", "Japanese Maple", 45, 75, ADA, self.ago(days=4))


def build_seed(now: datetime) -> SeedData:
    """Build the full seed relative to ``now``. Raises ``ValueError`` for a naive ``now``.

    Calling it twice with the same ``now`` gives equal data. No follows are
    seeded: a fake subscriber would receive real digest emails once they exist.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("build_seed requires a timezone-aware datetime")
    builder = _Builder(now)
    builder.build_elm_street()
    builder.build_balcony()
    builder.build_orchard()
    return builder.data
