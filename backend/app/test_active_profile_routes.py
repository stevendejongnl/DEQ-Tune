"""Checks the active-profile endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.active_profile import ActiveProfile
from app.active_profile_routes import get_active_profile
from app.deq_device import DeqDevice
from app.main import app
from app.testing.fake_deq import FakeDeq


@pytest.fixture(name="keeper")
def keeper_fixture(engine) -> ActiveProfile:
    """A keeper on the test database, with a fake unit that is not connected."""
    unit = DeqDevice(build_transport_function=FakeDeq)
    keeper = ActiveProfile(unit, lambda: Session(engine))
    app.dependency_overrides[get_active_profile] = lambda: keeper
    yield keeper
    app.dependency_overrides.pop(get_active_profile, None)


def custom_profile_id(client: TestClient) -> int:
    factory = client.get("/api/profiles").json()[0]
    return client.post(f"/api/profiles/{factory['id']}/duplicate").json()["id"]


def test_no_profile_is_active_at_first(seeded_client: TestClient, keeper):
    assert seeded_client.get("/api/active-profile").json() == {
        "profile_id": None,
        "status": "none",
        "problem": None,
        "equalizer_id": None,
        "source_mode": "CAR_SOURCE",
    }


def test_an_activated_profile_waits_for_the_unit(seeded_client: TestClient, keeper):
    profile_id = custom_profile_id(seeded_client)

    response = seeded_client.put("/api/active-profile", json={"profile_id": profile_id})

    assert response.status_code == 200
    assert response.json()["status"] == "waiting"
    assert seeded_client.get("/api/active-profile").json()["profile_id"] == profile_id


def test_activating_a_missing_profile_is_a_404(seeded_client: TestClient, keeper):
    response = seeded_client.put("/api/active-profile", json={"profile_id": 999999})
    assert response.status_code == 404


def test_deleting_the_active_profile_clears_it(seeded_client: TestClient, keeper):
    profile_id = custom_profile_id(seeded_client)
    seeded_client.put("/api/active-profile", json={"profile_id": profile_id})

    seeded_client.delete(f"/api/profiles/{profile_id}")

    assert seeded_client.get("/api/active-profile").json()["status"] == "none"


def test_activating_a_missing_eq_is_a_404(seeded_client: TestClient, keeper):
    response = seeded_client.put("/api/active-profile/equalizer", json={"equalizer_id": 999999})
    assert response.status_code == 404


def test_no_eq_is_a_valid_choice(seeded_client: TestClient, keeper):
    response = seeded_client.put("/api/active-profile/equalizer", json={"equalizer_id": None})

    assert response.status_code == 200
    assert response.json()["equalizer_id"] is None


def test_deleting_the_active_eq_clears_it(seeded_client: TestClient, keeper):
    equalizer_id = seeded_client.post(
        "/api/equalizers", json={"name": "Mine", "gains": [1.0] * 13}
    ).json()["id"]
    seeded_client.put("/api/active-profile/equalizer", json={"equalizer_id": equalizer_id})

    seeded_client.delete(f"/api/equalizers/{equalizer_id}")

    assert seeded_client.get("/api/active-profile").json()["equalizer_id"] is None


def test_a_source_chosen_offline_is_kept_for_the_next_link(seeded_client: TestClient, keeper):
    response = seeded_client.put("/api/active-profile/source", json={"name": "THROUGH"})

    assert response.status_code == 200
    assert response.json()["source_mode"] == "THROUGH"


def test_an_unknown_source_is_a_422(seeded_client: TestClient, keeper):
    response = seeded_client.put("/api/active-profile/source", json={"name": "RADIO"})
    assert response.status_code == 422
