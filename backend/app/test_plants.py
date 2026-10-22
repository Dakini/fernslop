import pytest

from app.store import store


def names(plants):
    return [plant["common_name"] for plant in plants]


# --- List ------------------------------------------------------------------


def test_list_plants_returns_all_51_reference_plants_in_seed_order(client):
    response = client.get("/api/plants")

    assert response.status_code == 200
    assert [plant["id"] for plant in response.json()] == [plant.id for plant in store.list_plants()]
    assert len(response.json()) == 51


def test_list_plants_is_identical_on_every_call(client):
    first = client.get("/api/plants").json()

    second = client.get("/api/plants").json()

    assert first == second


def test_list_plants_needs_no_actor_headers(client):
    response = client.get("/api/plants")

    assert response.status_code == 200


def test_list_plants_returns_full_plant_objects(client):
    plant = client.get("/api/plants").json()[0]

    assert set(plant) == {
        "id",
        "common_name",
        "scientific_name",
        "category",
        "description",
        "image_url",
        "water_every_days",
        "feed_every_days",
        "prune_every_days",
        "harvest_every_days",
        "source",
        "source_url",
    }


# --- Search ----------------------------------------------------------------


def test_search_matches_common_name_case_insensitively(client):
    response = client.get("/api/plants/search", params={"q": "TOM"})

    assert response.status_code == 200
    assert "Tomato" in names(response.json())


def test_search_matches_scientific_name(client):
    response = client.get("/api/plants/search", params={"q": "fragaria"})

    assert [plant["id"] for plant in response.json()] == ["plant-strawberry"]


def test_search_with_no_match_returns_empty_list(client):
    response = client.get("/api/plants/search", params={"q": "zzz"})

    assert response.status_code == 200
    assert response.json() == []


def test_search_trims_the_query_before_matching(client):
    response = client.get("/api/plants/search", params={"q": " tom "})

    assert "Tomato" in names(response.json())


def test_search_results_are_in_table_order(client):
    table = [plant.id for plant in store.list_plants()]

    result = [plant["id"] for plant in client.get("/api/plants/search", params={"q": "a"}).json()]

    assert result == [plant_id for plant_id in table if plant_id in result]


def test_search_has_no_cap_on_results(client):
    response = client.get("/api/plants/search", params={"q": "e"})

    assert len(response.json()) > 12


@pytest.mark.parametrize("q", [".*", ".", "t.m", "%", "*", "[a-z]", "^T", "to?"])
def test_search_treats_the_query_as_a_literal_string(client, q):
    response = client.get("/api/plants/search", params={"q": q})

    assert response.status_code == 200
    assert all(
        q.casefold() in plant["common_name"].casefold() or q.casefold() in plant["scientific_name"].casefold()
        for plant in response.json()
    )
    assert response.json() == [
        plant.model_dump(mode="json")
        for plant in store.list_plants()
        if q.casefold() in plant.common_name.casefold() or q.casefold() in plant.scientific_name.casefold()
    ]


@pytest.mark.parametrize("path", ["/api/plants/search", "/api/plants/search?q=", "/api/plants/search?q=%20%20"])
def test_search_with_missing_empty_or_blank_query_returns_first_12_plants(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert [plant["id"] for plant in response.json()] == [plant.id for plant in store.list_plants()[:12]]


def test_search_needs_no_actor_headers(client):
    response = client.get("/api/plants/search", params={"q": "rose"})

    assert response.status_code == 200


# --- OpenAPI -----------------------------------------------------------------


def test_plant_routes_appear_in_the_openapi_schema(client):
    paths = client.get("/api/openapi.json").json()["paths"]

    assert "get" in paths["/api/plants"]
    assert "get" in paths["/api/plants/search"]
    assert "post" in paths["/api/plants/identify"]
