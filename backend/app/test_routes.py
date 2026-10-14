from __future__ import annotations


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_profiles_empty_without_seed(client):
    resp = client.get("/api/profiles")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_profiles_after_seed(seeded_client):
    resp = seeded_client.get("/api/profiles")
    assert resp.status_code == 200
    assert len(resp.json()) == 14


def test_get_missing_profile_404(client):
    resp = client.get("/api/profiles/999")
    assert resp.status_code == 404


def test_create_custom_profile(seeded_client):
    factory = seeded_client.get("/api/profiles").json()[0]

    resp = seeded_client.post(
        "/api/profiles",
        json={"name": "My Custom EQ", "data": factory["data"]},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "My Custom EQ"
    assert body["source"] == "custom"


def test_factory_profile_is_read_only(seeded_client):
    factory_id = seeded_client.get("/api/profiles").json()[0]["id"]

    put_resp = seeded_client.put(f"/api/profiles/{factory_id}", json={"name": "Hacked"})
    assert put_resp.status_code == 409

    delete_resp = seeded_client.delete(f"/api/profiles/{factory_id}")
    assert delete_resp.status_code == 409


def test_duplicate_then_edit_and_delete(seeded_client):
    factory_id = seeded_client.get("/api/profiles").json()[0]["id"]

    dup_resp = seeded_client.post(f"/api/profiles/{factory_id}/duplicate")
    assert dup_resp.status_code == 201
    copy = dup_resp.json()
    assert copy["source"] == "custom"
    assert copy["name"].endswith("(copy)")

    put_resp = seeded_client.put(f"/api/profiles/{copy['id']}", json={"name": "Renamed"})
    assert put_resp.status_code == 200
    assert put_resp.json()["name"] == "Renamed"

    delete_resp = seeded_client.delete(f"/api/profiles/{copy['id']}")
    assert delete_resp.status_code == 204
    assert seeded_client.get(f"/api/profiles/{copy['id']}").status_code == 404


def test_a_factory_preset_takes_a_star(seeded_client):
    factory = seeded_client.get("/api/profiles").json()[0]
    assert factory["favorite"] is False

    response = seeded_client.put(f"/api/profiles/{factory['id']}/favorite", json={"favorite": True})

    assert response.status_code == 200
    assert seeded_client.get(f"/api/profiles/{factory['id']}").json()["favorite"] is True


def test_a_star_leaves_the_tuning_alone(seeded_client):
    factory = seeded_client.get("/api/profiles").json()[0]

    starred = seeded_client.put(
        f"/api/profiles/{factory['id']}/favorite", json={"favorite": True}
    ).json()

    assert starred["data"] == factory["data"]


def test_starring_a_missing_profile_is_a_404(client):
    response = client.put("/api/profiles/999999/favorite", json={"favorite": True})
    assert response.status_code == 404
