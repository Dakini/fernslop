import logging
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.errors import error_response
from app.store import get_store

router = APIRouter()
logger = logging.getLogger(__name__)

DATABASE_DOWN_MESSAGE = "The database is not answering."
# Set in the image from the FERNSLOP_IMAGE_TAG build arg (Dockerfile); deploy files never set it at run time.
IMAGE_TAG_ENV = "FERNSLOP_IMAGE_TAG"


@router.get("/health", include_in_schema=False, response_model=None)
def health() -> dict[str, str] | JSONResponse:
    """200 when the database answers ``SELECT 1`` within a few seconds, else 503 (infra/deploy.sh waits on this).

    The ping takes neither the store lock nor the PostgreSQL advisory lock (see ``SqlStore.ping``). Only the
    very first call in a process, if no request came before it, builds the store (tables, seed) as any route would.

    The 200 body is ``{"status": "ok"}``, plus ``"version": "<tag>"`` when the image was built with the
    ``FERNSLOP_IMAGE_TAG`` build arg (format ``YYYYMMDD-HHMMSS-shortsha``), so a deploy check can tell the new
    container from an old one. ``version`` holds only that tag (the route is public); without a tag, or with a
    blank one, it is left out. The 503 body has no ``version``.
    """
    try:
        get_store().ping()
    # Blind on purpose: raw driver errors (sqlite3, psycopg) are not wrapped by SQLAlchemy, and any failure
    # here means "not healthy", never a 500.
    except Exception as exc:  # noqa: BLE001
        logger.warning("Health check: database not answering: %s", exc)
        return error_response(503, DATABASE_DOWN_MESSAGE)
    body = {"status": "ok"}
    tag = os.environ.get(IMAGE_TAG_ENV, "").strip()
    if tag:
        body["version"] = tag
    return body
