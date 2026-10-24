"""Checks the library export and import against a real in-memory database."""

from __future__ import annotations

from sqlmodel import Session

from app.equalizers import seed_factory_equalizers

FLAT = [0.0] * 13


def custom_library(client) -> None:
    factory = client.get("/api/profiles").json()[0]
    client.post("/api/profiles", json={"name": "Dusty", "data": factory["data"]})
    client.post("/api/equalizers", json={"name": "Night drive", "gains": [1.0] + [0.0] * 12})
    client.put(f"/api/profiles/{factory['id']}/favorite", json={"favorite": True})


def test_the_export_holds_only_what_the_person_made(seeded_client, engine):
    with Session(engine) as session:
        seed_factory_equalizers(session)
    custom_library(seeded_client)

    library = seeded_client.get("/api/library/export").json()

    assert library["format"] == "deq-tune-library"
    assert [profile["name"] for profile in library["profiles"]] == ["Dusty"]
    assert [equalizer["name"] for equalizer in library["equalizers"]] == ["Night drive"]
    assert len(library["starred_factory_profiles"]) == 1
    assert "id" not in library["profiles"][0]


def test_an_import_into_another_database_adds_everything(seeded_client, engine):
    custom_library(seeded_client)
    library = seeded_client.get("/api/library/export").json()
    # A second install: delete what the first one made, keep the presets.
    for profile in seeded_client.get("/api/profiles").json():
        if profile["source"] == "custom":
            seeded_client.delete(f"/api/profiles/{profile['id']}")
        else:
            seeded_client.put(f"/api/profiles/{profile['id']}/favorite", json={"favorite": False})
    for equalizer in seeded_client.get("/api/equalizers").json():
        seeded_client.delete(f"/api/equalizers/{equalizer['id']}")

    result = seeded_client.post("/api/library/import", json=library).json()

    assert result == {"profiles_added": 1, "equalizers_added": 1, "skipped": 0, "stars_added": 1}
    assert seeded_client.get("/api/library/export").json() == library


def test_a_second_import_of_the_same_file_adds_nothing(seeded_client):
    custom_library(seeded_client)
    library = seeded_client.get("/api/library/export").json()

    result = seeded_client.post("/api/library/import", json=library).json()

    assert result == {"profiles_added": 0, "equalizers_added": 0, "skipped": 2, "stars_added": 0}
    assert len([p for p in seeded_client.get("/api/profiles").json() if p["source"] == "custom"]) == 1


def test_a_profile_with_the_same_name_but_another_tuning_is_added(seeded_client):
    custom_library(seeded_client)
    library = seeded_client.get("/api/library/export").json()
    equalizer = library["profiles"][0]["data"]["foundationEq"]
    equalizer["isLRMode"] = not equalizer["isLRMode"]

    result = seeded_client.post("/api/library/import", json=library).json()

    assert result["profiles_added"] == 1


def test_a_file_of_another_kind_is_refused(seeded_client):
    response = seeded_client.post("/api/library/import", json={"format": "something-else", "version": 1})

    assert response.status_code == 422


def test_a_file_from_a_newer_app_is_refused(seeded_client):
    response = seeded_client.post("/api/library/import", json={"format": "deq-tune-library", "version": 2})

    assert response.status_code == 422


def test_an_equalizer_out_of_range_is_refused(seeded_client):
    library = {"format": "deq-tune-library", "version": 1, "equalizers": [{"name": "Loud", "gains": [20.0] + [0.0] * 12}]}

    assert seeded_client.post("/api/library/import", json=library).status_code == 422
