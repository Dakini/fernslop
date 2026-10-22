"""Live updates. ``notify`` is called after every successful change to a room.

It does nothing yet; issue 011 makes it push to browsers. Routers call it as
``live.notify(room_id)`` (not ``from app.live import notify``) so tests can patch it.
"""


def notify(room_id: str) -> None:
    """Tell anyone watching ``room_id`` that its state changed."""
