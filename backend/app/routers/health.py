import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.errors import error_response
from app.store import get_store

router = APIRouter()
logger = logging.getLogger(__name__)

DATABASE_DOWN_MESSAGE = "The database is not answering."


@router.get("/health", include_in_schema=False, response_model=None)
def health() -> dict[str, str] | JSONResponse:
    """200 when the database answers ``SELECT 1`` within a few seconds, else 503 (infra/deploy.sh waits on this).

    The ping takes neither the store lock nor the PostgreSQL advisory lock (see ``SqlStore.ping``). Only the
    very first call in a process, if no request came before it, builds the store (tables, seed) as any route would.
    """
    try:
        get_store().ping()
    # Blind on purpose: raw driver errors (sqlite3, psycopg) are not wrapped by SQLAlchemy, and any failure
    # here means "not healthy", never a 500.
    except Exception as exc:  # noqa: BLE001
        logger.warning("Health check: database not answering: %s", exc)
        return error_response(503, DATABASE_DOWN_MESSAGE)
    return {"status": "ok"}
