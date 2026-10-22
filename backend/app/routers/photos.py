"""Photo upload and serving. Photos are kept through the store and are not tied to a room."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, UploadFile

from app import timestamps
from app.errors import ApiError
from app.models import Photo, StoredPhoto
from app.store import StoreProtocol, get_store
from app.uploads import read_image_upload

router = APIRouter(tags=["Photos"])

PHOTO_NOT_FOUND_MESSAGE = "Photo not found"
CACHE_CONTROL = "public, max-age=31536000, immutable"


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


@router.post("/photos", operation_id="uploadPhoto", status_code=201)
def upload_photo(file: UploadFile, store: Annotated[StoreProtocol, Depends(get_store)]) -> Photo:
    image = read_image_upload(file)
    photo_id = str(uuid.uuid4())
    url = f"/api/photos/{photo_id}"
    store.save_photo(
        StoredPhoto(
            id=photo_id,
            url=url,
            content_type=image.content_type,
            created_at=timestamps.now(),
            data=image.data,
        )
    )
    return Photo(id=photo_id, url=url)


@router.get("/photos/{photo_id}", operation_id="getPhoto", response_class=Response)
def get_photo(photo_id: str, store: Annotated[StoreProtocol, Depends(get_store)]) -> Response:
    photo = store.get_photo(photo_id) if _is_uuid(photo_id) else None
    if photo is None:
        raise ApiError(404, PHOTO_NOT_FOUND_MESSAGE)
    return Response(content=photo.data, media_type=photo.content_type, headers={"Cache-Control": CACHE_CONTROL})
