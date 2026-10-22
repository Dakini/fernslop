"""Routers included by ``app.main``.

To add a router, create a module in this package and add its ``router`` to
``routers`` below.
"""

from fastapi import APIRouter

from app.routers import health

routers: list[APIRouter] = [
    health.router,
]
