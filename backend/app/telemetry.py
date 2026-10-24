"""OpenTelemetry tracing: one server span per HTTP request, tagged with service, environment and version.

Every span's resource carries:

- ``service.name``: ``fernslop-backend``
- ``deployment.environment.name``: ``FERNSLOP_ENVIRONMENT`` (``dev``/``prod`` on the servers), else ``local``
- ``service.version``: ``FERNSLOP_IMAGE_TAG`` (baked into the image, see the Dockerfile), else ``unknown``

The standard OpenTelemetry variables still apply and win over the values above:

- ``OTEL_SERVICE_NAME`` and ``OTEL_RESOURCE_ATTRIBUTES`` override the resource
- ``OTEL_TRACES_EXPORTER``: ``otlp`` (configured by the ``OTEL_EXPORTER_OTLP_*`` variables), ``console``
  (stdout) or ``none``. Unset means ``none``: spans are made but never exported, so local runs and tests
  need no collector
- ``OTEL_SDK_DISABLED=true`` turns tracing off entirely

Request and response bodies and headers are never recorded.
"""

import logging
import os
import sys

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import OTELResourceDetector, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanProcessor,
)

logger = logging.getLogger(__name__)

SERVICE_NAME = "fernslop-backend"
ENVIRONMENT_ENV = "FERNSLOP_ENVIRONMENT"
# Same variable as app/routers/health.py: set in the image from a build arg, blank means unset.
IMAGE_TAG_ENV = "FERNSLOP_IMAGE_TAG"


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def build_resource() -> Resource:
    """Our defaults, overridden by OTEL_SERVICE_NAME and OTEL_RESOURCE_ATTRIBUTES."""
    defaults = Resource.create(
        {
            "service.name": SERVICE_NAME,
            "deployment.environment.name": _env(ENVIRONMENT_ENV) or "local",
            "service.version": _env(IMAGE_TAG_ENV) or "unknown",
        }
    )
    return defaults.merge(OTELResourceDetector().detect())


def _span_processors() -> list[SpanProcessor]:
    processors: list[SpanProcessor] = []
    for name in _env("OTEL_TRACES_EXPORTER").lower().split(","):
        name = name.strip()
        if name in ("", "none"):
            continue
        if name == "otlp":
            # Imported here so the protobuf/requests stack loads only when exporting
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            processors.append(BatchSpanProcessor(OTLPSpanExporter()))
        elif name == "console":
            processors.append(SimpleSpanProcessor(ConsoleSpanExporter(out=sys.stdout)))
        else:
            logger.warning("Ignoring unknown OTEL_TRACES_EXPORTER %r", name)
    return processors


def setup_telemetry(app: FastAPI) -> None:
    """Trace ``app``'s requests with its own TracerProvider (create_app runs once per test, so nothing global)."""
    if _env("OTEL_SDK_DISABLED").lower() == "true":
        return
    provider = TracerProvider(resource=build_resource())
    for processor in _span_processors():
        provider.add_span_processor(processor)
    # Only the server span per request, not the ASGI receive/send child spans
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, exclude_spans=["receive", "send"])
