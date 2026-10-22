"""Shared API models."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator

from app.text import INVALID_CHARACTERS_MESSAGE, has_invalid_characters
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


class RoomSummaryPlant(ApiModel):
    """A plant dot on a room thumbnail."""

    x_pct: Percent
    y_pct: Percent
    category: PlantCategory


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


AREA_LABEL_MAX_LENGTH = 40
AREA_LABEL_REQUIRED_MESSAGE = "An area needs a label"
AREA_LABEL_TOO_LONG_MESSAGE = f"An area label can be at most {AREA_LABEL_MAX_LENGTH} characters"

# Unlike plant coordinates, area numbers are rejected (400) outside range, never clamped.
# Strict: a string, boolean or null is not coerced into a number.
AreaPosition = Annotated[float, Field(strict=True, ge=0, le=100)]
AreaSize = Annotated[float, Field(strict=True, gt=0, le=100)]


def _check_area_label(value: str) -> str:
    label = value.strip()
    if not label:
        raise ValueError(AREA_LABEL_REQUIRED_MESSAGE)
    if len(label) > AREA_LABEL_MAX_LENGTH:
        raise ValueError(AREA_LABEL_TOO_LONG_MESSAGE)
    if has_invalid_characters(label):
        raise ValueError(INVALID_CHARACTERS_MESSAGE.format(label="An area label"))
    return label


class AreaInput(ApiModel):
    """Request body of ``addArea``. Unknown fields are ignored."""

    label: Annotated[str, Field(strict=True)]
    shape: AreaShape
    x_pct: AreaPosition
    y_pct: AreaPosition
    w_pct: AreaSize
    h_pct: AreaSize
    colour: AreaColour

    _trim_label = field_validator("label")(_check_area_label)


class AreaPatch(ApiModel):
    """Request body of ``updateArea``. Read ``model_fields_set`` to see what was sent; null is invalid."""

    label: Annotated[str, Field(strict=True)] = None  # type: ignore[assignment]
    shape: AreaShape = None  # type: ignore[assignment]
    x_pct: AreaPosition = None  # type: ignore[assignment]
    y_pct: AreaPosition = None  # type: ignore[assignment]
    w_pct: AreaSize = None  # type: ignore[assignment]
    h_pct: AreaSize = None  # type: ignore[assignment]
    colour: AreaColour = None  # type: ignore[assignment]

    _trim_label = field_validator("label")(_check_area_label)


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


class Photo(ApiModel):
    """What uploading a photo returns."""

    id: str
    url: str


class RoomSummary(ApiModel):
    """Just enough of a room to draw its thumbnail on the index page."""

    room: Room
    plants: list[RoomSummaryPlant]
    areas: list[RoomArea]


class RoomState(ApiModel):
    """Everything needed to render a room."""

    room: Room
    plants: list[RoomPlant]
    areas: list[RoomArea]
    feed: list[FeedEvent]


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


class IdentifyCandidate(ApiModel):
    """One possible match for an identified photo."""

    plant: Plant
    confidence: Annotated[float, Field(ge=0, le=1)]
