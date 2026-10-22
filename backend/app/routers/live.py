"""Live updates: ``GET /rooms/{roomId}/live`` streams ``change`` messages as Server-Sent Events.

It needs no actor headers, because the browser's ``EventSource`` cannot send them.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app import live
from app.errors import ApiError
from app.store import StoreProtocol, get_store

router = APIRouter(tags=["Realtime"])

ROOM_NOT_FOUND_MESSAGE = "Room not found"


@router.get("/rooms/{room_id}/live", operation_id="subscribe", response_class=StreamingResponse)
async def subscribe(room_id: str, store: Annotated[StoreProtocol, Depends(get_store)]) -> StreamingResponse:
    if store.get_room(room_id) is None:
        raise ApiError(404, ROOM_NOT_FOUND_MESSAGE)
    return StreamingResponse(
        live.event_stream(room_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
