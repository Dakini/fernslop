import io
import logging

import httpx
import pytest

from app.identify import (
    PLANTNET_URL,
    IdentifyError,
    PlantNetIdentifyProvider,
    StubIdentifyProvider,
    get_identify_provider,
)
from app.main import app
from app.models import IdentifyCandidate
from app.store import store
from app.uploads import ValidatedImage

JPEG_HEAD = b"\xff\xd8\xff\xe0"
PNG_HEAD = b"\x89PNG\r\n\x1a\n"


def jpeg_bytes(size=1234):
    return JPEG_HEAD + b"\x00" * (size - len(JPEG_HEAD))


def post_photo(client, data=None, filename="tomato.jpg", content_type="image/jpeg"):
    data = jpeg_bytes() if data is None else data
    return client.post("/api/plants/identify", files={"file": (filename, io.BytesIO(data), content_type)})


def candidate(plant_id, confidence):
    plant = next(p for p in store.list_plants() if p.id == plant_id)
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


def test_stub_gives_the_same_answer_for_the_same_upload_twice(client):
    first = post_photo(client).json()

    second = post_photo(client).json()

    assert first == second


def test_stub_returns_full_plant_objects(client):
    candidate_ = post_photo(client).json()[0]

    assert candidate_["plant"] == store.get_plant(candidate_["plant"]["id"]).model_dump(mode="json")


def test_stub_divides_confidences_by_four_when_filename_contains_blurry_in_any_case(client):
    response = post_photo(client, filename="My-BLURRY-fern.jpg")

    assert [c["confidence"] for c in response.json()] == [0.82 / 4, 0.11 / 4, 0.04 / 4]


def test_stub_hashes_utf16_code_units_so_astral_characters_count_as_two():
    # "🌿" is the surrogate pair D83C DF3F in UTF-16. Hash "🌿" + "5" by hand over those units.
    h = 0
    for unit in (0xD83C, 0xDF3F, ord("5")):
        h = (h * 31 + unit) % 2**32
    plants = store.list_plants()
    image = ValidatedImage(data=JPEG_HEAD + b"\x00", content_type="image/jpeg", filename="🌿")

    result = StubIdentifyProvider(plants).identify(image)

    assert [c.plant.id for c in result] == [plants[(h + i * 7) % 51].id for i in range(3)]


def test_stub_treats_a_missing_filename_as_empty():
    plants = store.list_plants()
    image = ValidatedImage(data=JPEG_HEAD + b"\x00", content_type="image/jpeg", filename=None)
    named = ValidatedImage(data=JPEG_HEAD + b"\x00", content_type="image/jpeg", filename="")

    provider = StubIdentifyProvider(plants)

    assert provider.identify(image) == provider.identify(named)


def test_stub_hash_is_pinned_for_empty_filename_and_a_one_digit_size():
    # h("" + "5") = ord("5") = 53; 53 mod 51 = 2, so rows 2, 9 and 16.
    plants = store.list_plants()
    image = ValidatedImage(data=b"12345", content_type="image/jpeg", filename=None)

    result = StubIdentifyProvider(plants).identify(image)

    assert [c.plant.id for c in result] == [plants[2].id, plants[9].id, plants[16].id]


def test_default_provider_is_the_stub(client):
    provider = get_identify_provider(store)

    assert isinstance(provider, StubIdentifyProvider)


# --- Results --------------------------------------------------------------


def test_unsorted_provider_results_are_sorted_by_confidence_descending(client, use_provider):
    use_provider(FakeProvider([candidate("plant-rose", 0.1), candidate("plant-mint", 0.7), candidate("plant-kale", 0.3)]))

    response = post_photo(client)

    assert [c["plant"]["id"] for c in response.json()] == ["plant-mint", "plant-kale", "plant-rose"]


def test_provider_returning_more_than_three_candidates_is_cut_to_the_best_three(client, use_provider):
    ids = ["plant-rose", "plant-mint", "plant-kale", "plant-pea"]
    use_provider(FakeProvider([candidate(i, c) for i, c in zip(ids, [0.1, 0.2, 0.3, 0.4])]))

    response = post_photo(client)

    assert [c["plant"]["id"] for c in response.json()] == ["plant-pea", "plant-kale", "plant-mint"]


def test_empty_provider_result_is_200_with_empty_list(client, use_provider):
    use_provider(FakeProvider([]))

    response = post_photo(client)

    assert response.status_code == 200
    assert response.json() == []


def test_provider_receives_the_validated_upload(client, use_provider):
    provider = use_provider(FakeProvider([]))

    post_photo(client, jpeg_bytes(100), filename="fern.jpg")

    assert provider.calls[0].data == jpeg_bytes(100)
    assert provider.calls[0].filename == "fern.jpg"
    assert provider.calls[0].content_type == "image/jpeg"


# --- Failures ----------------------------------------------------------------


def test_identify_error_from_provider_is_502_with_the_spec_message(client, use_provider):
    use_provider(FakeProvider(error=IdentifyError("upstream down")))

    response = post_photo(client)

    assert response.status_code == 502
    assert response.json() == {"message": "We couldn't identify that photo — try again"}


def test_any_other_provider_exception_is_a_500(use_provider):
    from fastapi.testclient import TestClient

    use_provider(FakeProvider(error=RuntimeError("boom")))
    # raise_server_exceptions=False so the 500 handler's response is returned instead of re-raised.
    client = TestClient(app, raise_server_exceptions=False)

    response = post_photo(client)

    assert response.status_code == 500
    assert response.json() == {"message": "Something went wrong. Please try again."}


# --- Upload validation (through the shared module) -----------------------------------


def test_missing_file_field_is_400(client):
    response = client.post("/api/plants/identify", data={"other": "x"})

    assert response.status_code == 400
    assert response.json() == {"message": "file: Field required"}


def test_non_image_declared_type_is_415(client):
    response = post_photo(client, b"hello", filename="a.txt", content_type="text/plain")

    assert response.status_code == 415
    assert response.json() == {"message": "Please use a JPG, PNG or WebP image"}


def test_png_declared_as_jpeg_is_415(client):
    response = post_photo(client, PNG_HEAD + b"data", content_type="image/jpeg")

    assert response.status_code == 415


def test_empty_file_is_415(client):
    response = post_photo(client, b"")

    assert response.status_code == 415


def test_file_of_5_mib_plus_one_byte_is_413(client):
    response = post_photo(client, jpeg_bytes(5 * 1024 * 1024 + 1))

    assert response.status_code == 413
    assert response.json() == {"message": "That photo is over 5 MB"}


def test_file_of_exactly_5_mib_is_accepted(client):
    response = post_photo(client, jpeg_bytes(5 * 1024 * 1024))

    assert response.status_code == 200


def test_identify_only_reads_plants_from_the_store(client):
    from app.store import get_store

    class RecordingStore:
        def __init__(self):
            self.calls = []

        def __getattr__(self, name):
            self.calls.append(name)
            return getattr(store, name)

    recording = RecordingStore()
    app.dependency_overrides[get_store] = lambda: recording
    try:
        response = post_photo(client)
    finally:
        app.dependency_overrides.pop(get_store, None)

    assert response.status_code == 200
    assert set(recording.calls) == {"list_plants"}


# --- Pl@ntNet provider ---------------------------------------------------------

API_KEY = "sekrit-key-123"


def plantnet(handler, key=API_KEY):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return PlantNetIdentifyProvider(store.list_plants(), key, client=client)


def respond(body, status=200):
    return lambda request: httpx.Response(status, json=body)


def hit(name, score):
    return {"score": score, "species": {"scientificNameWithoutAuthor": name}}


def jpeg_image(filename="fern.jpg"):
    return ValidatedImage(data=jpeg_bytes(50), content_type="image/jpeg", filename=filename)


def test_plantnet_request_is_one_post_to_the_identify_url_with_api_key_query():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"results": []})

    plantnet(handler).identify(jpeg_image())

    assert len(seen) == 1
    assert seen[0].method == "POST"
    assert seen[0].url.copy_with(query=None) == httpx.URL(PLANTNET_URL)
    assert seen[0].url.params["api-key"] == API_KEY


def test_plantnet_request_is_multipart_with_images_file_part_and_organs_auto():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"results": []})
    image = ValidatedImage(data=PNG_HEAD + b"pixels", content_type="image/png", filename="leaf.png")

    plantnet(handler).identify(image)

    body = seen[0].read()
    assert seen[0].headers["content-type"].startswith("multipart/form-data")
    assert b'name="images"; filename="leaf.png"' in body
    assert b"Content-Type: image/png" in body
    assert PNG_HEAD + b"pixels" in body
    assert b'name="organs"' in body
    assert b"\r\n\r\nauto\r\n" in body


def test_plantnet_request_has_a_10_second_timeout():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"results": []})

    plantnet(handler).identify(jpeg_image())

    assert seen[0].extensions["timeout"] == {"connect": 10, "read": 10, "write": 10, "pool": 10}


def test_plantnet_maps_a_result_to_the_reference_plant_with_score_as_confidence():
    provider = plantnet(respond({"results": [hit("Ocimum basilicum", 0.73)]}))

    result = provider.identify(jpeg_image())

    assert [(c.plant.id, c.confidence) for c in result] == [("plant-basil", 0.73)]


def test_plantnet_matches_scientific_name_trimmed_and_case_insensitively():
    provider = plantnet(respond({"results": [hit("  MENTHA spicata ", 0.5)]}))

    result = provider.identify(jpeg_image())

    assert [c.plant.id for c in result] == ["plant-mint"]


def test_plantnet_drops_results_that_match_no_reference_plant():
    provider = plantnet(respond({"results": [hit("Nonexistus plantus", 0.9), hit("Ocimum basilicum", 0.1)]}))

    result = provider.identify(jpeg_image())

    assert [c.plant.id for c in result] == ["plant-basil"]


def test_plantnet_keeps_the_highest_score_when_a_plant_is_matched_twice():
    provider = plantnet(respond({"results": [hit("Ocimum basilicum", 0.2), hit("ocimum basilicum", 0.6), hit("Ocimum basilicum", 0.4)]}))

    result = provider.identify(jpeg_image())

    assert [(c.plant.id, c.confidence) for c in result] == [("plant-basil", 0.6)]


def test_plantnet_with_no_match_returns_an_empty_list_and_the_route_is_200(client, use_provider):
    use_provider(plantnet(respond({"results": [hit("Nonexistus plantus", 0.9)]})))

    response = post_photo(client)

    assert response.status_code == 200
    assert response.json() == []


def test_plantnet_with_empty_results_returns_an_empty_list():
    assert plantnet(respond({"results": []})).identify(jpeg_image()) == []


def test_plantnet_ignores_malformed_result_items_and_out_of_range_scores():
    results = [{"species": {}}, "junk", hit("Mentha spicata", 7), hit("Ocimum basilicum", 0.3)]

    result = plantnet(respond({"results": results})).identify(jpeg_image())

    assert [c.plant.id for c in result] == ["plant-basil"]


def test_plantnet_results_flow_through_the_route_best_three_first(client, use_provider):
    names = ["Ocimum basilicum", "Mentha spicata", "Salvia rosmarinus", "Thymus vulgaris"]
    use_provider(plantnet(respond({"results": [hit(n, s) for n, s in zip(names, [0.1, 0.4, 0.3, 0.2])]})))

    response = post_photo(client)

    assert [c["plant"]["id"] for c in response.json()] == ["plant-mint", "plant-rosemary", "plant-thyme"]


def test_plantnet_timeout_raises_identify_error():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(IdentifyError):
        plantnet(handler).identify(jpeg_image())


def test_plantnet_connection_error_raises_identify_error():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(IdentifyError):
        plantnet(handler).identify(jpeg_image())


@pytest.mark.parametrize("status", [300, 301, 400, 401, 404, 429, 500, 503])
def test_plantnet_non_2xx_status_raises_identify_error(status):
    provider = plantnet(respond({"results": [hit("Ocimum basilicum", 0.5)]}, status=status))

    with pytest.raises(IdentifyError):
        provider.identify(jpeg_image())


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"<html>nope</html>"),
        httpx.Response(200, content=b""),
        httpx.Response(200, json={"other": []}),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"results": "none"}),
        httpx.Response(200, json={"results": None}),
    ],
)
def test_plantnet_body_that_is_not_json_or_lacks_results_raises_identify_error(response):
    with pytest.raises(IdentifyError):
        plantnet(lambda request: response).identify(jpeg_image())


def test_plantnet_webp_upload_raises_identify_error_without_calling_upstream():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"results": []})
    image = ValidatedImage(data=b"RIFF\x00\x00\x00\x00WEBPVP8 ", content_type="image/webp", filename="a.webp")

    with pytest.raises(IdentifyError):
        plantnet(handler).identify(image)

    assert calls == []


def test_plantnet_failure_is_502_through_the_route(client, use_provider):
    use_provider(plantnet(respond({}, status=500)))

    response = post_photo(client)

    assert response.status_code == 502
    assert response.json() == {"message": "We couldn't identify that photo — try again"}


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


def test_plantnet_identify_error_has_no_key_in_message_or_cause():
    def handler(request):
        raise httpx.ConnectError(f"cannot reach {request.url}", request=request)

    with pytest.raises(IdentifyError) as excinfo:
        plantnet(handler).identify(jpeg_image())

    assert API_KEY not in str(excinfo.value)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True


def test_plantnet_httpx_request_log_line_has_the_key_redacted(caplog):
    caplog.set_level(logging.DEBUG)
    provider = plantnet(respond({"results": []}))

    provider.identify(jpeg_image())

    assert API_KEY not in caplog.text


# --- Provider selection from env -----------------------------------------------


def select(monkeypatch, provider=None, key=None):
    for name, value in (("FERNSLOP_IDENTIFY_PROVIDER", provider), ("FERNSLOP_IDENTIFY_API_KEY", key)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    return get_identify_provider(store)


def test_env_plantnet_with_a_key_selects_the_plantnet_provider(monkeypatch):
    assert isinstance(select(monkeypatch, "plantnet", "abc"), PlantNetIdentifyProvider)


@pytest.mark.parametrize(
    ("provider", "key"),
    [
        (None, None),
        (None, "abc"),
        ("stub", "abc"),
        ("openai", "abc"),
        ("plantnet", None),
        ("plantnet", ""),
        ("plantnet", "   "),
    ],
)
def test_env_any_other_combination_selects_the_stub(monkeypatch, provider, key):
    assert isinstance(select(monkeypatch, provider, key), StubIdentifyProvider)
