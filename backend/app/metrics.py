"""Application metrics, sent with the same resource as the traces (service, environment, version; see telemetry.py).

- ``fernslop.gardens.created``: gardens (rooms) created
- ``fernslop.garden_plants.created``: plants added to a garden
- ``fernslop.component_creation.failures``: failed creates of a garden, plant or area, by ``component`` and
  ``http.response.status_code`` (400 bad input, 404 missing room/plant, 409 garden full, 429 rate limited, 500)
- ``fernslop.garden.participants.active``: distinct devices that changed any garden in the last 15 minutes
  (the frontend sends ``X-Device-Id`` on writes only, so people who only look are not counted)
- ``fernslop.photos.uploaded``: photos uploaded for posts (``uploadPhoto``; identify photos are not stored or counted)
- ``fernslop.plant_search.empty``: plant searches the person settled on that found nothing, reported by the frontend
  once the person stops typing for 1.5 seconds, or sooner on Enter, the Photo tab or closing the dialog
  (``recordSearchMiss``), not on every keystroke.
  The query is not a metric
  label (user text would make one series per query); ``record_empty_search`` logs it instead, as ``search.term``
  on the ``fernslop.search`` logger, which telemetry.py exports as OpenTelemetry logs (Loki)

Created and failed counts come from ``MetricsMiddleware``, keyed on the route's operationId and the response status, so a
create only counts once its transaction has committed. Instruments are no-ops until ``install`` is called.
"""

import logging
import threading
import time
from collections.abc import Iterable

from opentelemetry.metrics import CallbackOptions, Meter, MeterProvider, NoOpMeterProvider, Observation
from starlette.types import ASGIApp, Message, Receive, Scope, Send

METER_NAME = "fernslop"
ACTIVE_WINDOW_SECONDS = 15 * 60
# Caps memory if many devices write within one window; the oldest are dropped first
MAX_TRACKED_DEVICES = 10_000

# operationId (openapi.yaml) of the create routes -> the component they create
CREATE_OPERATIONS = {"createRoom": "garden", "addPlant": "plant", "addArea": "area"}
UPLOAD_PHOTO_OPERATION = "uploadPhoto"
WRITE_METHODS = {"POST", "PATCH", "DELETE"}
SEARCH_TERM_MAX_LENGTH = 100

search_logger = logging.getLogger("fernslop.search")
# INFO is below the root logger's default WARNING; the empty-search records are the point of this logger
search_logger.setLevel(logging.INFO)


class ActiveDevices:
    """Device ids by when they last wrote, kept in memory only and never exported."""

    def __init__(self) -> None:
        self._last_seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def seen(self, device_id: str, now: float) -> None:
        with self._lock:
            self._last_seen.pop(device_id, None)
            self._last_seen[device_id] = now
            if len(self._last_seen) > MAX_TRACKED_DEVICES:
                del self._last_seen[next(iter(self._last_seen))]

    def count(self, now: float) -> int:
        with self._lock:
            cutoff = now - ACTIVE_WINDOW_SECONDS
            self._last_seen = {device: at for device, at in self._last_seen.items() if at >= cutoff}
            return len(self._last_seen)


class AppMetrics:
    def __init__(self, meter: Meter) -> None:
        self.active_devices = ActiveDevices()
        self.gardens_created = meter.create_counter(
            "fernslop.gardens.created", unit="{garden}", description="Gardens created"
        )
        self.garden_plants_created = meter.create_counter(
            "fernslop.garden_plants.created", unit="{plant}", description="Plants added to a garden"
        )
        self.creation_failures = meter.create_counter(
            "fernslop.component_creation.failures",
            unit="{failure}",
            description="Failed creates of a garden, plant or area",
        )
        self.photos_uploaded = meter.create_counter(
            "fernslop.photos.uploaded", unit="{photo}", description="Photos uploaded for posts"
        )
        self.empty_plant_searches = meter.create_counter(
            "fernslop.plant_search.empty", unit="{search}", description="Plant searches that found nothing"
        )
        # Start each series at 0, so Prometheus sees the first garden, plant, photo or empty search as an increase
        for counter in (
            self.gardens_created,
            self.garden_plants_created,
            self.photos_uploaded,
            self.empty_plant_searches,
        ):
            counter.add(0)
        meter.create_observable_gauge(
            "fernslop.garden.participants.active",
            callbacks=[self._observe_participants],
            unit="{participant}",
            description=f"Devices that changed a garden in the last {ACTIVE_WINDOW_SECONDS // 60} minutes",
        )

    def _observe_participants(self, _options: CallbackOptions) -> Iterable[Observation]:
        yield Observation(self.active_devices.count(time.monotonic()))


_current = AppMetrics(NoOpMeterProvider().get_meter(METER_NAME))


def install(provider: MeterProvider) -> None:
    """Record into ``provider`` from now on (called by telemetry.setup_telemetry)."""
    global _current
    _current = AppMetrics(provider.get_meter(METER_NAME))


def current() -> AppMetrics:
    return _current


def record_empty_search(term: str) -> None:
    """Count a plant search that found nothing and log its (already normalised) term."""
    current().empty_plant_searches.add(1)
    search_logger.info("Plant search found nothing", extra={"search.term": term[:SEARCH_TERM_MAX_LENGTH]})


def _header(scope: Scope, name: bytes) -> str:
    for key, value in scope["headers"]:
        if key == name:
            return value.decode("latin-1").strip()
    return ""


def _record(scope: Scope, status: int) -> None:
    # Set by the router once a route matched; unknown paths have none
    route = scope.get("route")
    method = scope["method"]
    metrics = current()
    operation_id = getattr(route, "operation_id", None) or ""
    if operation_id == UPLOAD_PHOTO_OPERATION and status < 400:
        metrics.photos_uploaded.add(1)
    component = CREATE_OPERATIONS.get(operation_id)
    if component is not None:
        if status >= 400:
            metrics.creation_failures.add(
                1, {"component": component, "http.response.status_code": status}
            )
        elif component == "garden":
            metrics.gardens_created.add(1)
        elif component == "plant":
            metrics.garden_plants_created.add(1)
    device_id = _header(scope, b"x-device-id")
    if device_id and method in WRITE_METHODS and route is not None and status < 400:
        metrics.active_devices.seen(device_id, time.monotonic())


class MetricsMiddleware:
    """Pure ASGI, so streamed responses (the live feed) pass through untouched."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # Stays 500 if the app raises before it starts a response
        status = 500

        async def send_and_note_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_and_note_status)
        finally:
            _record(scope, status)
