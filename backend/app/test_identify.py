import io
import logging

import httpx
import pytest

from app.identify import PlantNetIdentifyProvider, get_identify_provider
from app.main import app
from app.models import IdentifyCandidate
from app.store import get_store
from app.uploads import ValidatedImage

JPEG_HEAD = b"\xff\xd8\xff\xe0"


def jpeg_bytes(size=1234):
    return JPEG_HEAD + b"\x00" * (size - len(JPEG_HEAD))


def post_photo(client, data=None, filename="tomato.jpg", content_type="image/jpeg"):
    data = jpeg_bytes() if data is None else data
    return client.post("/api/plants/identify", files={"file": (filename, io.BytesIO(data), content_type)})


def candidate(plant_id, confidence):
    plant = next(p for p in get_store().list_plants() if p.id == plant_id)
    return IdentifyCandidate(plant=plant, confidence=confidence)


class FakeProvider:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def identify(self, image):
        self.calls.append(image)
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def use_provider():
    def install(provider):
        app.dependency_overrides[get_identify_provider] = lambda: provider
        return provider

    yield install
    app.dependency_overrides.pop(get_identify_provider, None)


# --- Stub provider -----------------------------------------------------------


def test_stub_for_tomato_jpg_of_1234_bytes_picks_daffodil_cosmos_and_fiddle_leaf_fig(client):
    # Worked out by hand: h = fold(h * 31 + code unit) mod 2^32 over "tomato.jpg1234" = 3325661631.
    # 3325661631 mod 51 = 30, so the picks are table rows 30, 37 and 44.
    response = post_photo(client, jpeg_bytes(1234), filename="tomato.jpg")

    assert response.status_code == 200
    body = response.json()
    assert [c["plant"]["id"] for c in body] == ["plant-daffodil", "plant-cosmos", "plant-fiddle-leaf-fig"]
    assert [c["confidence"] for c in body] == [0.82, 0.11, 0.04]


# --- Results --------------------------------------------------------------


def test_provider_results_are_sorted_by_confidence_and_cut_to_the_best_three(client, use_provider):
    ids = ["plant-rose", "plant-mint", "plant-kale", "plant-pea"]
    use_provider(FakeProvider([candidate(i, c) for i, c in zip(ids, [0.3, 0.1, 0.2, 0.4])]))

    response = post_photo(client)

    assert [c["plant"]["id"] for c in response.json()] == ["plant-pea", "plant-rose", "plant-kale"]


# --- Failures ----------------------------------------------------------------


# --- Upload validation (through the shared module) -----------------------------------


def test_file_over_5_mib_is_413_and_exactly_5_mib_is_accepted(client):
    response = post_photo(client, jpeg_bytes(5 * 1024 * 1024 + 1))

    assert response.status_code == 413
    assert response.json() == {"message": "That photo is over 5 MB"}
    assert post_photo(client, jpeg_bytes(5 * 1024 * 1024)).status_code == 200


# --- Pl@ntNet provider ---------------------------------------------------------

API_KEY = "sekrit-key-123"


def plantnet(handler, key=API_KEY):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return PlantNetIdentifyProvider(get_store().list_plants(), key, client=client)


def respond(body, status=200):
    return lambda request: httpx.Response(status, json=body)


def hit(name, score):
    return {"score": score, "species": {"scientificNameWithoutAuthor": name}}


def jpeg_image(filename="fern.jpg"):
    return ValidatedImage(data=jpeg_bytes(50), content_type="image/jpeg", filename=filename)


def test_plantnet_maps_a_result_to_the_reference_plant_with_score_as_confidence():
    provider = plantnet(respond({"results": [hit("Ocimum basilicum", 0.73)]}))

    result = provider.identify(jpeg_image())

    assert [(c.plant.id, c.confidence) for c in result] == [("plant-basil", 0.73)]


# --- Pl@ntNet: the key never leaks ----------------------------------------------


def test_plantnet_failing_upstream_never_leaks_the_key_to_the_response_or_logs(client, use_provider, caplog):
    caplog.set_level(logging.DEBUG)

    def handler(request):
        raise httpx.ConnectError(f"cannot reach {request.url}", request=request)
    use_provider(plantnet(handler))

    response = post_photo(client)

    assert response.status_code == 502
    assert API_KEY not in response.text
    assert API_KEY not in str(dict(response.headers))
    assert API_KEY not in caplog.text


# --- Provider selection from env -----------------------------------------------


