import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.errors import register_error_handlers
from app.routers import routers
from app.static import mount_frontend

API_PREFIX = "/api"

DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]


def cors_origins() -> list[str]:
    """Allowed origins: FERNSLOP_CORS_ORIGINS (comma-separated) or the defaults."""
    raw = os.environ.get("FERNSLOP_CORS_ORIGINS")
    if raw is None:
        return DEFAULT_CORS_ORIGINS
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def api_docs_enabled() -> bool:
    """Swagger UI, ReDoc and the OpenAPI JSON are served unless FERNSLOP_API_DOCS=0 (production)."""
    return os.environ.get("FERNSLOP_API_DOCS", "1").strip() != "0"


def create_app() -> FastAPI:
    docs = api_docs_enabled()
    app = FastAPI(
        title="Fernslop API",
        version="0.1.0",
        docs_url=f"{API_PREFIX}/docs" if docs else None,
        redoc_url=f"{API_PREFIX}/redoc" if docs else None,
        openapi_url=f"{API_PREFIX}/openapi.json" if docs else None,
    )
    register_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["content-type", "x-device-id", "x-actor-name"],
    )
    for router in routers:
        app.include_router(router, prefix=API_PREFIX)
    mount_frontend(app, API_PREFIX)
    return app


app = create_app()
