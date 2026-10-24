import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from app import metrics, telemetry
from app.main import create_app
from app.test_photos import make_image

ADA = {"x-device-id": "device-ada", "x-actor-name": "Ada"}
BO = {"x-device-id": "device-bo", "x-actor-name": "Bo"}


@pytest.fixture
def reader(monkeypatch):
    # Exporting to a collector is the only other way to see metrics, so swap the reader the env would pick
    in_memory = InMemoryMetricReader()
    monkeypatch.setattr(telemetry, "_metric_readers", lambda: [in_memory])
    monkeypatch.setattr(metrics, "_current", metrics.current())
    monkeypatch.setenv("FERNSLOP_ENVIRONMENT", "dev")
    monkeypatch.setenv("FERNSLOP_IMAGE_TAG", "20261023-120000-abc1234")
    return in_memory


@pytest.fixture
def client(reader):
    return TestClient(create_app())


def _points(reader, name):
    """[(attributes, value)] of metric ``name``, plus the resource it was sent with."""
    data = reader.get_metrics_data()
    for resource_metrics in data.resource_metrics if data else []:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == name:
                    points = [(dict(p.attributes), p.value) for p in metric.data.data_points]
                    return points, dict(resource_metrics.resource.attributes)
    return [], {}


def _new_garden(client) -> str:
    return client.post("/api/rooms", json={"name": "Allotment"}).json()["id"]


def test_created_gardens_and_plants_are_counted_with_environment_and_version(client, reader):
    room_id = _new_garden(client)
    plant_id = client.get("/api/plants").json()[0]["id"]

    client.post(f"/api/rooms/{room_id}/plants", json={"plant_id": plant_id}, headers=ADA)

    gardens, resource = _points(reader, "fernslop.gardens.created")
    plants, _ = _points(reader, "fernslop.garden_plants.created")
    assert gardens == [({}, 1)]
    assert plants == [({}, 1)]
    assert resource["deployment.environment.name"] == "dev"
    assert resource["service.version"] == "20261023-120000-abc1234"


def test_failed_plant_create_counts_a_failure_and_no_plant(client, reader):
    room_id = _new_garden(client)

    response = client.post(f"/api/rooms/{room_id}/plants", json={"plant_id": "no-such-plant"}, headers=ADA)

    assert response.status_code == 404
    failures, _ = _points(reader, "fernslop.component_creation.failures")
    assert failures == [({"component": "plant", "http.response.status_code": 404}, 1)]
    assert _points(reader, "fernslop.garden_plants.created")[0] == [({}, 0)]


def _search_terms(caplog) -> list[str]:
    return [getattr(record, "search.term") for record in caplog.records if record.name == "fernslop.search"]


def test_searching_alone_records_no_miss(client, reader, caplog):
    # The search box searches on every keystroke
    for q in ("z", "zz", "zzzz-not-a-plant"):
        assert client.get("/api/plants/search", params={"q": q}).json() == []

    assert _points(reader, "fernslop.plant_search.empty")[0] == [({}, 0)]
    assert _search_terms(caplog) == []


def test_reported_miss_is_counted_and_logs_its_normalised_term(client, reader, caplog):
    response = client.post("/api/plants/search/misses", json={"q": "  Purple Kale  "})

    assert response.status_code == 204
    assert _points(reader, "fernslop.plant_search.empty")[0] == [({}, 1)]
    assert _search_terms(caplog) == ["purple kale"]


@pytest.mark.parametrize("q", ["tomato", "   "])
def test_reported_miss_that_is_not_one_is_ignored(client, reader, caplog, q):
    # A term that finds plants, or no term at all, is not a miss whatever the frontend says
    assert client.post("/api/plants/search/misses", json={"q": q}).status_code == 204

    assert _points(reader, "fernslop.plant_search.empty")[0] == [({}, 0)]
    assert _search_terms(caplog) == []


def test_reported_miss_needs_a_string(client):
    assert client.post("/api/plants/search/misses", json={"q": 3}).status_code == 400


def test_uploaded_photos_are_counted(client, reader):
    response = client.post("/api/photos", files={"file": ("leaf.png", make_image("PNG"), "image/png")})

    assert response.status_code == 201
    assert _points(reader, "fernslop.photos.uploaded")[0] == [({}, 1)]


def test_active_participants_counts_each_writing_device_once(client, reader):
    room_id = _new_garden(client)
    area = {"label": "Bed", "shape": "rect", "x_pct": 10, "y_pct": 10, "w_pct": 20, "h_pct": 20, "colour": "soil"}

    for headers in (ADA, ADA, BO):
        client.post(f"/api/rooms/{room_id}/areas", json=area, headers=headers)

    active, _ = _points(reader, "fernslop.garden.participants.active")
    assert active == [({}, 2)]
