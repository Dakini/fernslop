"""Per-client-IP rate limits on writes, kept in memory for the single uvicorn worker.

Each write route lists its limit as a dependency, so the check runs before the body is read
or the store is touched::

    @router.post("/rooms", dependencies=[rate_limited(CREATE_ROOM)])

Over the limit the call answers 429 with ``{"message": ...}`` and a ``Retry-After`` header in
whole seconds. ``GET`` routes, ``/live`` streams and ``/api/health`` list no limit.

Buckets and their defaults (count per period, per client IP; an IPv6 client is keyed by its
/64), each overridable by the environment variable shown, as ``<count>/<second|minute|hour|day>``:

- ``create_room``  10/hour    ``FERNSLOP_RATE_LIMIT_CREATE_ROOM``
- ``delete_room``  10/hour    ``FERNSLOP_RATE_LIMIT_DELETE_ROOM``
- ``upload_photo`` 30/hour    ``FERNSLOP_RATE_LIMIT_UPLOAD_PHOTO``
- ``identify``     20/hour    ``FERNSLOP_RATE_LIMIT_IDENTIFY``
- ``follow``       10/hour    ``FERNSLOP_RATE_LIMIT_FOLLOW``
- ``write``        120/minute ``FERNSLOP_RATE_LIMIT_WRITE`` (plants, care, areas, posts, undo, unfollow)

``FERNSLOP_RATE_LIMIT=off`` turns every limit off. Settings are read when the limiter is
(re)built: at start-up and on ``reset()``.

The client IP is ``request.client.host``. Behind Caddy, uvicorn's ``--proxy-headers`` sets it
from ``X-Forwarded-For``, but only for a peer listed in ``FORWARDED_ALLOW_IPS``; the app itself
never reads that header, so a client cannot pick its own bucket.

Windows are fixed per bucket and IP. Expired windows are dropped as the limiter is used, so
many distinct IPs cannot grow memory without bound. A lock guards the state, since sync routes
run in the thread pool.
"""

import ipaddress
import math
import os
import threading
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Request
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

from app.errors import ApiError

DISABLE_ENV = "FERNSLOP_RATE_LIMIT"

CREATE_ROOM = "create_room"
DELETE_ROOM = "delete_room"
UPLOAD_PHOTO = "upload_photo"
IDENTIFY = "identify"
FOLLOW = "follow"
WRITE = "write"

DEFAULT_LIMITS = {
    CREATE_ROOM: "10/hour",
    DELETE_ROOM: "10/hour",
    UPLOAD_PHOTO: "30/hour",
    IDENTIFY: "20/hour",
    FOLLOW: "10/hour",
    WRITE: "120/minute",
}

PERIOD_SECONDS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}

TOO_FAST_MESSAGE = "You're going a bit fast. Try again in {seconds} seconds."
FILE_REQUIRED_MESSAGE = "file: Field required"


@dataclass(frozen=True)
class Limit:
    count: int
    period: float


def parse_limit(value: str) -> Limit:
    """``"10/hour"`` -> ``Limit(10, 3600)``."""
    count, _, unit = value.strip().partition("/")
    return Limit(int(count), PERIOD_SECONDS[unit.strip().lower().removesuffix("s")])


def env_name(bucket: str) -> str:
    return f"FERNSLOP_RATE_LIMIT_{bucket.upper()}"


def client_key(host: str | None) -> str:
    """The bucket key for a client address: the IP, or the /64 network for IPv6."""
    if not host:
        return "unknown"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.IPv6Network((address, 64), strict=False))
    return str(address)


class RateLimiter:
    def __init__(self) -> None:
        self.enabled = os.environ.get(DISABLE_ENV, "").strip().lower() not in ("off", "0", "false", "no")
        self.limits = {
            bucket: parse_limit(os.environ.get(env_name(bucket)) or default)
            for bucket, default in DEFAULT_LIMITS.items()
        }
        self._windows: dict[tuple[str, str], tuple[float, int]] = {}  # (bucket, key) -> (start, count)
        self._lock = threading.Lock()
        self._next_sweep = 0.0

    def hit(self, bucket: str, key: str, now: float | None = None) -> int | None:
        """Count one call. ``None`` if allowed, else the whole seconds until the window resets."""
        if not self.enabled:
            return None
        limit = self.limits[bucket]
        now = time.monotonic() if now is None else now
        with self._lock:
            self._sweep(now)
            start, count = self._windows.get((bucket, key), (now, 0))
            if now - start >= limit.period:
                start, count = now, 0
            if count >= limit.count:
                return max(1, math.ceil(start + limit.period - now))
            self._windows[(bucket, key)] = (start, count + 1)
            return None

    def _sweep(self, now: float) -> None:
        """Drop expired windows, at most once a second (the shortest period)."""
        if now < self._next_sweep:
            return
        self._next_sweep = now + 1
        expired = [
            entry
            for entry, (start, _) in self._windows.items()
            if now - start >= self.limits[entry[0]].period
        ]
        for entry in expired:
            del self._windows[entry]

    def __len__(self) -> int:
        return len(self._windows)


_limiter = RateLimiter()


def get_limiter() -> RateLimiter:
    return _limiter


def reset() -> None:
    """Forget every count and re-read the settings from the environment (tests use this)."""
    global _limiter
    _limiter = RateLimiter()


def rate_limited(bucket: str) -> Any:
    """A route dependency that counts the call against ``bucket`` for the client's IP."""
    if bucket not in DEFAULT_LIMITS:
        raise ValueError(f"unknown rate-limit bucket {bucket!r}")

    async def check(request: Request) -> None:
        host = request.client.host if request.client else None
        retry_after = get_limiter().hit(bucket, client_key(host))
        if retry_after is not None:
            raise HTTPException(
                429,
                TOO_FAST_MESSAGE.format(seconds=retry_after),
                headers={"Retry-After": str(retry_after)},
            )

    return Depends(check)


async def read_upload_file(request: Request) -> AsyncIterator[UploadFile]:
    """The multipart ``file`` field, read only when this dependency runs.

    FastAPI parses a declared ``UploadFile`` parameter before any dependency, which would read the
    whole upload before the rate limit is checked. Routes take ``file`` through this dependency
    instead, listed after their ``rate_limited`` dependency.
    """
    form = await request.form()
    try:
        file = form.get("file")
        if not isinstance(file, UploadFile):
            raise ApiError(400, FILE_REQUIRED_MESSAGE)
        yield file
    finally:
        await form.close()
