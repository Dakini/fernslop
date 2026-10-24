"""Plant reference table: list, search and identify."""

from itertools import islice
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile

from app import metrics
from app.errors import ApiError
from app.identify import (
    IDENTIFY_FAILED_MESSAGE,
    IdentifyError,
    IdentifyProvider,
    get_identify_provider,
)
from app.models import IdentifyCandidate, Plant
from app.rate_limit import IDENTIFY, IDENTIFY_DAILY, rate_limited, read_upload_file
from app.store import StoreProtocol, get_store
from app.uploads import read_image_upload

router = APIRouter(tags=["Plants"])

DEFAULT_SEARCH_LIMIT = 12
MAX_IDENTIFY_CANDIDATES = 3


@router.get("/plants", operation_id="listPlants")
def list_plants(store: Annotated[StoreProtocol, Depends(get_store)]) -> list[Plant]:
    return store.list_plants()


@router.get("/plants/search", operation_id="searchPlants")
def search_plants(store: Annotated[StoreProtocol, Depends(get_store)], q: str = "") -> list[Plant]:
    plants = store.list_plants()
    needle = q.strip().casefold()
    if not needle:
        return plants[:DEFAULT_SEARCH_LIMIT]
    matches = (
        plant
        for plant in plants
        if needle in plant.common_name.casefold() or needle in plant.scientific_name.casefold()
    )
    found = list(islice(matches, DEFAULT_SEARCH_LIMIT))
    if not found:
        metrics.record_empty_search(needle)
    return found


@router.post(
    "/plants/identify",
    operation_id="identifyPlant",
    dependencies=[rate_limited(IDENTIFY), rate_limited(IDENTIFY_DAILY)],
)
def identify_plant(
    file: Annotated[UploadFile, Depends(read_upload_file)],
    provider: Annotated[IdentifyProvider, Depends(get_identify_provider)],
) -> list[IdentifyCandidate]:
    image = read_image_upload(file)
    try:
        candidates = provider.identify(image)
    except IdentifyError:
        raise ApiError(502, IDENTIFY_FAILED_MESSAGE) from None
    ranked = sorted(candidates, key=lambda candidate: candidate.confidence, reverse=True)
    return ranked[:MAX_IDENTIFY_CANDIDATES]
