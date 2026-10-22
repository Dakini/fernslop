"""Routers included by ``app.main``.

To add a router, create a module in this package and add its ``router`` to
``routers`` below.
"""

from fastapi import APIRouter

from app.routers import health, plants, room_plants, rooms

routers: list[APIRouter] = [
    health.router,
    plants.router,
    rooms.router,
    room_plants.router,
]
