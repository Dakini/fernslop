"""Routers included by ``app.main``.

To add a router, create a module in this package and add its ``router`` to
``routers`` below.
"""

from fastapi import APIRouter

from app.routers import areas, follows, health, photos, plants, posts, room_plants, rooms

routers: list[APIRouter] = [
    health.router,
    plants.router,
    rooms.router,
    room_plants.router,
    areas.router,
    follows.router,
    photos.router,
    posts.router,
]
