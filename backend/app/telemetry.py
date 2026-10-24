"""OpenTelemetry traces, metrics and logs, tagged with service, environment and version.

Traces have one server span per HTTP request; the metrics, and the one logger that is exported, are described in
app/metrics.py. All three share a resource with:

- ``service.name``: ``fernslop-backend``
- ``deployment.environment.name``: ``FERNSLOP_ENVIRONMENT`` (``dev``/``prod`` on the servers), else ``local``
- ``service.version``: ``FERNSLOP_IMAGE_TAG`` (baked into the image, see the Dockerfile), else ``unknown``

The standard OpenTelemetry variables still apply and win over the values above:

- ``OTEL_SERVICE_NAME`` and ``OTEL_RESOURCE_ATTRIBUTES`` override the resource
- ``OTEL_TRACES_EXPORTER``, ``OTEL_METRICS_EXPORTER`` and ``OTEL_LOGS_EXPORTER``: ``otlp`` (configured by the ``OTEL_EXPORTER_OTLP_*``
  variables), ``console`` (stdout) or ``none``. Unset means ``none``: nothing is exported, so local runs and
  tests need no collector. Metrics are exported every ``OTEL_METRIC_EXPORT_INTERVAL`` ms (default 60000)
- ``OTEL_SDK_DISABLED=true`` turns all three off entirely

Request and response bodies and headers are never recorded.
"""

import logging
import os
import sys
import threading

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.sdk._logs import LoggerProvider, LogRecordProcessor
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import OTELResourceDetector, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanProcessor,
)

from app import metrics

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


def _exporter_names(variable: str) -> list[str]:
    names = []
    for name in _env(variable).lower().split(","):
        name = name.strip()
        if name in ("", "none"):
            continue
        if name in ("otlp", "console"):
            names.append(name)
        else:
            logger.warning("Ignoring unknown %s %r", variable, name)
    return names


def _span_processors() -> list[SpanProcessor]:
    processors: list[SpanProcessor] = []
    for name in _exporter_names("OTEL_TRACES_EXPORTER"):
        if name == "otlp":
            # Imported here so the protobuf/requests stack loads only when exporting
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            processors.append(BatchSpanProcessor(OTLPSpanExporter()))
        else:
            processors.append(SimpleSpanProcessor(ConsoleSpanExporter(out=sys.stdout)))
    return processors


def _metric_readers() -> list[MetricReader]:
    readers: list[MetricReader] = []
    for name in _exporter_names("OTEL_METRICS_EXPORTER"):
        if name == "otlp":
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

            readers.append(PeriodicExportingMetricReader(OTLPMetricExporter()))
        else:
            readers.append(PeriodicExportingMetricReader(ConsoleMetricExporter(out=sys.stdout)))
    return readers


def _log_processors() -> list[LogRecordProcessor]:
    processors: list[LogRecordProcessor] = []
    for name in _exporter_names("OTEL_LOGS_EXPORTER"):
        if name == "otlp":
            from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

            processors.append(BatchLogRecordProcessor(OTLPLogExporter()))
        else:
            processors.append(SimpleLogRecordProcessor(ConsoleLogRecordExporter(out=sys.stdout)))
    return processors


def _export_search_logs(provider: LoggerProvider) -> None:
    """Send metrics.search_logger's records to ``provider``, replacing the handler of an earlier app."""
    for handler in list(metrics.search_logger.handlers):
        if isinstance(handler, LoggingHandler):
            metrics.search_logger.removeHandler(handler)
    metrics.search_logger.addHandler(LoggingHandler(level=logging.INFO, logger_provider=provider))


def setup_telemetry(app: FastAPI) -> None:
    """Trace ``app``'s requests with its own TracerProvider and count its metrics.

    create_app runs once per test, so the OpenTelemetry globals are never set: the TracerProvider is passed to
    the instrumentor, and app.metrics records into the MeterProvider and LoggerProvider of the app created last.
    """
    if _env("OTEL_SDK_DISABLED").lower() == "true":
        return
    resource = build_resource()
    tracer_provider = TracerProvider(resource=resource)
    for processor in _span_processors():
        tracer_provider.add_span_processor(processor)
    meter_provider = MeterProvider(resource=resource, metric_readers=_metric_readers())
    metrics.install(meter_provider)
    # Export the counters' starting 0 now instead of after the first interval, so Prometheus counts the first
    # events too; in a thread so start-up never waits on the collector
    threading.Thread(target=meter_provider.force_flush, name="otel-first-export", daemon=True).start()
    logger_provider = LoggerProvider(resource=resource)
    for log_processor in _log_processors():
        logger_provider.add_log_record_processor(log_processor)
    _export_search_logs(logger_provider)
    app.add_middleware(metrics.MetricsMiddleware)
    # Only the server span per request, not the ASGI receive/send child spans
    FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider, exclude_spans=["receive", "send"])
