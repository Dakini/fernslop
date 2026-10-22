"""Routers included by ``app.main``.

To add a router, create a module in this package and add its ``router`` to
``routers`` below.
"""

from fastapi import APIRouter

from app.routers import areas, feed_events, follows, health, live, photos, plants, posts, room_plants, rooms

routers: list[APIRouter] = [
    health.router,
    plants.router,
    rooms.router,
    room_plants.router,
    areas.router,
    feed_events.router,
    follows.router,
    photos.router,
    posts.router,
    live.router,
]
