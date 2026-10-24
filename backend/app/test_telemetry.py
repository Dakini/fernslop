import json

from fastapi.testclient import TestClient

from app.main import create_app


def _health_span(monkeypatch, capsys, **env) -> dict | None:
    """GET /api/health on a fresh app with the console exporter; return the one span it printed, if any."""
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "console")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    client = TestClient(create_app())
    capsys.readouterr()

    response = client.get("/api/health", headers={"x-device-id": "device-secret", "x-actor-name": "Ada"})

    assert response.status_code == 200
    out = capsys.readouterr().out
    return json.loads(out) if out.strip() else None


def test_request_span_carries_service_environment_and_version_but_no_headers(monkeypatch, capsys):
    span = _health_span(
        monkeypatch, capsys, FERNSLOP_ENVIRONMENT="dev", FERNSLOP_IMAGE_TAG="20261023-120000-abc1234"
    )

    assert span["kind"] == "SpanKind.SERVER"
    resource = span["resource"]["attributes"]
    assert resource["service.name"] == "fernslop-backend"
    assert resource["deployment.environment.name"] == "dev"
    assert resource["service.version"] == "20261023-120000-abc1234"
    assert "device-secret" not in json.dumps(span)
    assert "Ada" not in json.dumps(span)


def test_request_span_without_environment_or_version_says_local_and_unknown(monkeypatch, capsys):
    monkeypatch.delenv("FERNSLOP_ENVIRONMENT", raising=False)

    span = _health_span(monkeypatch, capsys, FERNSLOP_IMAGE_TAG=" ")

    resource = span["resource"]["attributes"]
    assert resource["deployment.environment.name"] == "local"
    assert resource["service.version"] == "unknown"


def test_standard_otel_variables_override_the_resource(monkeypatch, capsys):
    span = _health_span(
        monkeypatch,
        capsys,
        FERNSLOP_ENVIRONMENT="dev",
        OTEL_SERVICE_NAME="other-service",
        OTEL_RESOURCE_ATTRIBUTES="deployment.environment.name=staging",
    )

    resource = span["resource"]["attributes"]
    assert resource["service.name"] == "other-service"
    assert resource["deployment.environment.name"] == "staging"


def test_sdk_disabled_serves_requests_and_records_no_spans(monkeypatch, capsys):
    span = _health_span(monkeypatch, capsys, OTEL_SDK_DISABLED="true")

    assert span is None
