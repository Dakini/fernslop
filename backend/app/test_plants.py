import pytest

from app.store import get_store


def names(plants):
    return [plant["common_name"] for plant in plants]


# --- List ------------------------------------------------------------------


def test_list_plants_returns_all_51_reference_plants_in_seed_order(client):
    response = client.get("/api/plants")

    assert response.status_code == 200
    assert [plant["id"] for plant in response.json()] == [plant.id for plant in get_store().list_plants()]
    assert len(response.json()) == 51
    assert {"id", "common_name", "scientific_name", "category", "water_every_days", "image_url"} <= set(response.json()[0])


# --- Search ----------------------------------------------------------------


def test_search_matches_common_name_case_insensitively(client):
    response = client.get("/api/plants/search", params={"q": "TOM"})

    assert response.status_code == 200
    assert "Tomato" in names(response.json())


def test_search_matches_scientific_name(client):
    response = client.get("/api/plants/search", params={"q": "fragaria"})

    assert [plant["id"] for plant in response.json()] == ["plant-strawberry"]


def test_search_returns_at_most_12_matches_in_seed_order(client):
    response = client.get("/api/plants/search", params={"q": "a"})

    matches = [
        plant.id
        for plant in get_store().list_plants()
        if "a" in plant.common_name.casefold() or "a" in plant.scientific_name.casefold()
    ]
    assert len(matches) > 12  # otherwise the cap is not exercised
    assert [plant["id"] for plant in response.json()] == matches[:12]


@pytest.mark.parametrize("q", [".*", "%"])
def test_search_treats_the_query_as_a_literal_string(client, q):
    response = client.get("/api/plants/search", params={"q": q})

    assert response.status_code == 200
    assert all(
        q.casefold() in plant["common_name"].casefold() or q.casefold() in plant["scientific_name"].casefold()
        for plant in response.json()
    )
    assert response.json() == [
        plant.model_dump(mode="json")
        for plant in get_store().list_plants()
        if q.casefold() in plant.common_name.casefold() or q.casefold() in plant.scientific_name.casefold()
    ]


@pytest.mark.parametrize("path", ["/api/plants/search", "/api/plants/search?q=%20%20"])
def test_search_with_missing_empty_or_blank_query_returns_first_12_plants(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert [plant["id"] for plant in response.json()] == [plant.id for plant in get_store().list_plants()[:12]]


# --- OpenAPI -----------------------------------------------------------------


