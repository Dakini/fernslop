"""Live updates. ``notify`` is called after every successful change to a room.

Each open ``GET /rooms/{roomId}/live`` stream owns a subscriber: an ``asyncio.Queue`` plus the
event loop it was created on. Route handlers run in worker threads, so ``notify`` never touches
asyncio objects directly; it only asks each subscriber's loop to deliver, with
``loop.call_soon_threadsafe``. Everything runs in one process (see issue 090 for more).

Routers call it as ``live.notify(room_id)`` (not ``from app.live import notify``) so tests can
patch it.
"""

import asyncio
import logging
import os
import threading
from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

PING_ENV = "FERNSLOP_SSE_PING_SECONDS"
DEFAULT_PING_SECONDS = 25.0
PING_FRAME = ": ping\n\n"


class _Subscriber:
    def __init__(self, room_id: str) -> None:
        self.room_id = room_id
        self.loop = asyncio.get_running_loop()
        # One slot: notifies the stream has not read yet merge into a single message.
        self.queue: asyncio.Queue[None] = asyncio.Queue(maxsize=1)

    def deliver(self) -> None:
        """Runs on the subscriber's own loop."""
        try:
            self.queue.put_nowait(None)
        except asyncio.QueueFull:
            pass


_lock = threading.Lock()
_subscribers: dict[str, list[_Subscriber]] = {}


def _subscribe(room_id: str) -> _Subscriber:
    subscriber = _Subscriber(room_id)
    with _lock:
        _subscribers.setdefault(room_id, []).append(subscriber)
    return subscriber


def _unsubscribe(subscriber: _Subscriber) -> None:
    with _lock:
        subscribers = _subscribers.get(subscriber.room_id)
        if subscribers is None:
            return
        if subscriber in subscribers:
            subscribers.remove(subscriber)
        if not subscribers:
            del _subscribers[subscriber.room_id]


def subscriber_count(room_id: str | None = None) -> int:
    """How many streams are open for ``room_id`` (all rooms if ``None``)."""
    with _lock:
        if room_id is not None:
            return len(_subscribers.get(room_id, ()))
        return sum(len(subscribers) for subscribers in _subscribers.values())


def notify(room_id: str) -> None:
    """Tell anyone watching ``room_id`` that its state changed. Safe to call from any thread."""
    with _lock:
        subscribers = list(_subscribers.get(room_id, ()))
    for subscriber in subscribers:
        try:
            subscriber.loop.call_soon_threadsafe(subscriber.deliver)
        except RuntimeError:  # that stream's loop has closed
            continue
        except Exception:  # never let a broken stream fail someone else's mutation
            logger.exception("Could not notify a live subscriber of room %s", room_id)


def ping_seconds() -> float:
    """The ping interval from ``FERNSLOP_SSE_PING_SECONDS``; unset, non-numeric or <= 0 gives 25."""
    try:
        seconds = float(os.environ.get(PING_ENV, ""))
    except ValueError:
        return DEFAULT_PING_SECONDS
    if not seconds > 0 or seconds == float("inf"):  # also rejects nan
        return DEFAULT_PING_SECONDS
    return seconds


async def event_stream(room_id: str) -> AsyncIterator[str]:
    """SSE frames for one stream. It subscribes when first run and unsubscribes when it ends."""
    interval = ping_seconds()
    subscriber = _subscribe(room_id)
    try:
        yield PING_FRAME
        while True:
            try:
                await asyncio.wait_for(subscriber.queue.get(), timeout=interval)
            except TimeoutError:
                yield PING_FRAME
            else:
                yield f"event: change\ndata: {room_id}\n\n"
    finally:
        _unsubscribe(subscriber)
