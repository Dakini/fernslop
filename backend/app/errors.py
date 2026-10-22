"""Error types and handlers. Every error body is ``{"message": "..."}``."""

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

INTERNAL_ERROR_MESSAGE = "Something went wrong. Please try again."


class ApiError(Exception):
    """Raise this from a route to return ``status_code`` with ``{"message": message}``."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"message": message})


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.status_code, exc.message)


def _validation_message(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Invalid request."
    first = errors[0]
    if first.get("type") == "json_invalid":
        return "Request body is not valid JSON."
    loc = first.get("loc") or ()
    field = loc[-1] if loc else "body"
    return f"{field}: {first.get('msg', 'Invalid value')}"


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # The spec reserves 422 for markCare, which raises ApiError(422, ...) itself.
    return error_response(400, _validation_message(exc))


_HTTP_MESSAGES = {
    404: "No such endpoint.",
    405: "Method not allowed.",
}


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = _HTTP_MESSAGES.get(exc.status_code)
    if message is None:
        message = exc.detail if isinstance(exc.detail, str) and exc.detail else None
    if message is None:
        message = HTTPStatus(exc.status_code).phrase
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": message},
        headers=getattr(exc, "headers", None),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return error_response(500, INTERNAL_ERROR_MESSAGE)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
