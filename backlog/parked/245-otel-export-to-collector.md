# [otel] Follow-up: ship telemetry to a collector or vendor
**What:** Choose a backend (e.g. a hosted OTLP vendor or a collector sidecar on the instance) and set the `OTEL_EXPORTER_OTLP_*` settings for dev and prod.
**Why:** Moved out of [#243](../243-otel-backend-sdk-and-resource.md) and [#244](../244-otel-environment-in-container.md), which only produce telemetry with the right attributes.
**Edge cases:** Keep any API key out of the image and git (instance `app.env` or SSM); the instance is small, so a sidecar costs memory; dev holds real data, so check spans carry no personal data.
