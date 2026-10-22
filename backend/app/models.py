"""Shared API models."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from app.timestamps import format_timestamp


class ApiModel(BaseModel):
    """Base class for every request and response model."""


class Error(BaseModel):
    """The body of every error response."""

    message: str


Timestamp = Annotated[
    datetime,
    PlainSerializer(format_timestamp, return_type=str, when_used="json"),
]


# --- Record models -----------------------------------------------------------
#
# Field names, nullability and enums follow the matching schema in openapi.yaml.
# Request-only and response-only shapes are added by the issue that serves them.

Percent = Annotated[float, Field(ge=0, le=100)]

PlantCategory = Literal["flower", "vegetable", "herb", "houseplant", "shrub", "tree"]
AreaShape = Literal["rect", "ellipse"]
AreaColour = Literal["soil", "water", "sage", "clay"]
FeedEventType = Literal["plant_added", "plant_removed", "plant_moved", "care_done", "area_changed", "post"]


class Plant(ApiModel):
    """A row of the plant reference table."""

    id: str
    common_name: str
    scientific_name: str
    category: PlantCategory
    description: str
    image_url: str | None
    water_every_days: int | None
    feed_every_days: int | None
    prune_every_days: int | None
    harvest_every_days: int | None
    source: str
    source_url: str


class Room(ApiModel):
    id: str
    name: str
    description: str
    region: str
    created_at: Timestamp
    last_activity_at: Timestamp


class RoomPlant(ApiModel):
    id: str
    room_id: str
    plant_id: str
    nickname: str | None
    x_pct: Percent
    y_pct: Percent
    last_watered_at: Timestamp | None
    last_fed_at: Timestamp | None
    last_pruned_at: Timestamp | None
    last_harvested_at: Timestamp | None
    added_by_name: str
    created_at: Timestamp
    deleted_at: Timestamp | None


class RoomArea(ApiModel):
    id: str
    room_id: str
    label: str
    shape: AreaShape
    x_pct: Percent
    y_pct: Percent
    w_pct: Percent
    h_pct: Percent
    colour: AreaColour
    deleted_at: Timestamp | None


class RestorePlantPayload(ApiModel):
    kind: Literal["restore_plant"]
    room_plant: RoomPlant


class DeletePlantPayload(ApiModel):
    kind: Literal["delete_plant"]
    room_plant_id: str


class RestoreAreaPayload(ApiModel):
    kind: Literal["restore_area"]
    area: RoomArea | None
    area_id: str


UndoPayload = Annotated[
    RestorePlantPayload | DeletePlantPayload | RestoreAreaPayload,
    Field(discriminator="kind"),
]
"""What undoing an event needs, discriminated on ``kind``."""


class FeedEvent(ApiModel):
    id: str
    room_id: str
    type: FeedEventType
    actor_name: str
    device_id: str
    room_plant_id: str | None
    text: str
    photo_url: str | None
    undo_payload: UndoPayload | None
    undone_at: Timestamp | None
    created_at: Timestamp


class RoomFollow(ApiModel):
    """The public view of a follow. The unsubscribe token is deliberately left out."""

    model_config = ConfigDict(extra="forbid")

    id: str
    room_id: str
    email: str
    created_at: Timestamp


# --- Stored-only types -------------------------------------------------------


class StoredFollow(RoomFollow):
    """A follow as kept by the store, with its secret unsubscribe token."""

    unsubscribe_token: str

    def to_public(self) -> RoomFollow:
        """The follow as the API shows it, without the token."""
        return RoomFollow(id=self.id, room_id=self.room_id, email=self.email, created_at=self.created_at)


class StoredPhoto(ApiModel):
    """An uploaded photo with its bytes. Never serialised as an API response."""

    id: str
    url: str
    content_type: str
    created_at: Timestamp
    data: bytes
