"""JSON request bodies: capped in size, and only accepted as ``application/json``.

Routes take ``body: JsonBody`` as a parameter and call ``body.object()`` when they want the
parsed object. Reading is an async dependency, so the route itself can be a plain ``def``
that FastAPI runs in its thread pool, away from the event loop the store would block.

Requiring ``application/json`` means a cross-site page cannot send these requests as a CORS
"simple" request (``text/plain``) without a preflight, which the CORS allow-list rejects.
"""

import json
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request

from app.errors import ApiError

MAX_JSON_BODY_BYTES = 64 * 1024

TOO_LARGE_MESSAGE = "Request body is too large"
NOT_JSON_TYPE_MESSAGE = "Send the request body as application/json"
INVALID_JSON_MESSAGE = "Request body is not valid JSON"
NOT_AN_OBJECT_MESSAGE = "Request body must be a JSON object"


@dataclass(frozen=True)
class RawJsonBody:
    """The body bytes and declared type, read but not yet checked or parsed."""

    content_type: str
    data: bytes

    def object(self) -> dict[str, Any]:
        """The body as a JSON object. 415 unless sent as ``application/json``, 400 if it is not an object."""
        media_type = self.content_type.split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            raise ApiError(415, NOT_JSON_TYPE_MESSAGE)
        try:
            parsed = json.loads(self.data)
        except ValueError:  # invalid JSON, or bytes that are not UTF-8
            raise ApiError(400, INVALID_JSON_MESSAGE) from None
        if not isinstance(parsed, dict):
            raise ApiError(400, NOT_AN_OBJECT_MESSAGE)
        return parsed


async def read_json_body(request: Request) -> RawJsonBody:
    """Dependency: read at most ``MAX_JSON_BODY_BYTES`` of the body, or reject with a 413."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_JSON_BODY_BYTES:
        raise ApiError(413, TOO_LARGE_MESSAGE)
    chunks = bytearray()
    async for chunk in request.stream():
        chunks += chunk
        if len(chunks) > MAX_JSON_BODY_BYTES:
            raise ApiError(413, TOO_LARGE_MESSAGE)
    return RawJsonBody(content_type=request.headers.get("content-type", ""), data=bytes(chunks))


JsonBody = Annotated[RawJsonBody, Depends(read_json_body)]
