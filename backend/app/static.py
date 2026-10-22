"""Serve the built frontend (a client-only SPA) from the API process.

Configuration: ``FERNSLOP_STATIC_DIR`` points at the frontend build output
(``frontend/dist/client``). Unset, or not a directory, nothing is served and the
app is API-only. Real files are served as they are; any other non-API path gets
the SPA shell so client-side routes work on reload.
"""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

STATIC_DIR_ENV = "FERNSLOP_STATIC_DIR"
SHELL_FILE = "_shell.html"


def static_dir() -> Path | None:
    raw = os.environ.get(STATIC_DIR_ENV)
    if not raw:
        return None
    directory = Path(raw).resolve()
    return directory if (directory / SHELL_FILE).is_file() else None


def mount_frontend(app: FastAPI, api_prefix: str) -> None:
    directory = static_dir()
    if directory is None:
        return
    api_root = api_prefix.strip("/")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        if path == api_root or path.startswith(f"{api_root}/"):
            raise HTTPException(404)
        candidate = (directory / path).resolve()
        if candidate.is_file() and candidate.is_relative_to(directory) and candidate.name != SHELL_FILE:
            return FileResponse(candidate)
        return FileResponse(directory / SHELL_FILE)
