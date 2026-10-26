"""Checks the Filter screen's endpoints against a fake unit."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.active_profile import ActiveProfile
from app.active_profile_routes import get_active_profile
from app.deq_blob import CrossoverSetting as StoredFilter
from app.deq_blob import UserConfiguration
from app.deq_device import DeqDevice
from app.deq_dsp import FilterSlope, build_crossover_payload, crossover_slot_settings
from app.deq_session import CONFIG_ID_CROSSOVER_STANDARD
from app.device_routes import get_device
from app.main import app
from app.testing.fake_deq import FakeDeq


def car_configuration() -> UserConfiguration:
    """The car's speaker mode and the filters its unit held on 2026-10-08."""
    configuration = UserConfiguration(speaker_mode=3)
    configuration.crossovers = [
        StoredFilter(frequency=6, slope=0),
        StoredFilter(frequency=8, slope=0),
        StoredFilter(frequency=5, slope=3),
        StoredFilter(frequency=3, slope=4),
    ]
    return configuration


@pytest.fixture
def fake_unit() -> FakeDeq:
    return FakeDeq(configuration=car_configuration())


@pytest.fixture
def keeper(fake_unit: FakeDeq, engine) -> ActiveProfile:
    unit = DeqDevice(build_transport_function=lambda: fake_unit)
    unit.connect()
    return ActiveProfile(unit, lambda: Session(engine))


@pytest.fixture(name="crossover_client")
def crossover_client_fixture(
    seeded_client: TestClient, keeper: ActiveProfile
) -> TestClient:
    app.dependency_overrides[get_device] = lambda: keeper.unit
    app.dependency_overrides[get_active_profile] = lambda: keeper
    yield seeded_client
    app.dependency_overrides.pop(get_device, None)
    app.dependency_overrides.pop(get_active_profile, None)


def test_the_cars_mode_shows_front_rear_and_subwoofer(crossover_client: TestClient) -> None:
    body = crossover_client.get("/api/device/crossover").json()

    assert body["speaker_mode"] == "STANDARD_FL_FR_RL_RR_SW"
    assert [
        (one["speaker"], one["kind"], one["owner"], one["cutoff_position"], one["slope"])
        for one in body["filters"]
    ] == [
        ("front", "high_pass", "profile", 6, 0),
        ("rear", "high_pass", "profile", 8, 0),
        ("subwoofer", "low_pass", "unit", 3, 4),
    ]
    assert body["filters"][2]["cutoffs_hz"][3] == 50.0
    assert len(body["filters"][2]["cutoffs_hz"]) == 11


def test_the_front_and_rear_come_from_the_active_profile(
    crossover_client: TestClient, keeper: ActiveProfile
) -> None:
    """A push sends the profile's filters, so the screen shows those and not
    the older ones the blob may hold."""
    profile = crossover_client.get("/api/profiles").json()[0]
    keeper.activate(profile["id"])
    front = profile["data"]["filter"]["front"]

    body = crossover_client.get("/api/device/crossover").json()

    assert body["filters"][0]["cutoff_position"] == front["cutoff_hpf"]
    assert body["filters"][0]["slope"] == front["slope_hpf"]


def test_a_subwoofer_change_is_stored_and_played(
    crossover_client: TestClient, fake_unit: FakeDeq
) -> None:
    response = crossover_client.put(
        "/api/device/crossover",
        json={"speaker": "subwoofer", "cutoff_position": 5, "slope": 2},
    )

    assert response.status_code == 200
    assert response.json()["filters"][2]["cutoff_position"] == 5
    assert fake_unit.configuration.crossovers[3] == StoredFilter(frequency=5, slope=2)
    crossover_write = [
        one
        for one in fake_unit.exchanges
        if one.request.command_id == 0x05
        and int.from_bytes(one.request.body[:4], "little") == CONFIG_ID_CROSSOVER_STANDARD
    ][-1]
    # No profile is active, so the blob's own front and rear go out.
    expected = build_crossover_payload(
        "standard",
        crossover_slot_settings(
            "standard",
            [6, 8, 0, 0, 5],
            [FilterSlope.PASS, FilterSlope.PASS, FilterSlope.PASS, FilterSlope.PASS, FilterSlope(2)],
        ),
    )
    assert crossover_write.request.body[4:] == expected


def test_a_filter_the_mode_does_not_use_is_refused(
    crossover_client: TestClient, fake_unit: FakeDeq
) -> None:
    response = crossover_client.put(
        "/api/device/crossover",
        json={"speaker": "rear_subwoofer", "cutoff_position": 5, "slope": 2},
    )

    assert response.status_code == 409
    assert fake_unit.configuration.crossovers[2] == StoredFilter(frequency=5, slope=3)


def test_a_profile_filter_cannot_be_changed_here(crossover_client: TestClient) -> None:
    response = crossover_client.put(
        "/api/device/crossover",
        json={"speaker": "front", "cutoff_position": 5, "slope": 2},
    )

    assert response.status_code == 422


def test_a_network_mode_unit_answers_409(
    crossover_client: TestClient, fake_unit: FakeDeq
) -> None:
    fake_unit.configuration.speaker_mode = 7

    assert crossover_client.get("/api/device/crossover").status_code == 409


def test_the_crossover_needs_a_unit(seeded_client: TestClient) -> None:
    app.dependency_overrides[get_device] = lambda: DeqDevice(
        build_transport_function=lambda: FakeDeq(answers=False)
    )
    try:
        assert seeded_client.get("/api/device/crossover").status_code == 503
    finally:
        app.dependency_overrides.pop(get_device, None)


def test_the_speaker_mode_changes_and_the_subwoofer_filter_leaves_the_list(
    crossover_client: TestClient, fake_unit: FakeDeq
) -> None:
    response = crossover_client.put(
        "/api/device/crossover/speaker-mode", json={"speaker_mode": "STANDARD_FL_FR_RL_RR"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["speaker_mode"] == "STANDARD_FL_FR_RL_RR"
    assert [one["speaker"] for one in body["filters"]] == ["front", "rear"]
    assert fake_unit.configuration.speaker_mode == 2
    # The stored subwoofer filter stays, for the day a subwoofer comes back.
    assert fake_unit.configuration.crossovers[3] == StoredFilter(frequency=3, slope=4)


def test_a_mode_change_keeps_the_active_profile_applied(
    crossover_client: TestClient, keeper: ActiveProfile
) -> None:
    profile = crossover_client.get("/api/profiles").json()[0]
    keeper.activate(profile["id"])
    assert crossover_client.get("/api/active-profile").json()["status"] == "applied"

    crossover_client.put(
        "/api/device/crossover/speaker-mode", json={"speaker_mode": "STANDARD_FL_FR_RL_RR"}
    )

    assert crossover_client.get("/api/active-profile").json()["status"] == "applied"


def test_the_list_offers_only_the_standard_modes(crossover_client: TestClient) -> None:
    body = crossover_client.get("/api/device/crossover").json()

    assert body["speaker_modes"] == [
        "STANDARD_FL_FR",
        "STANDARD_FL_FR_RL_RR",
        "STANDARD_FL_FR_RL_RR_SW",
        "STANDARD_FL_FR_RLSW_RRSW",
        "STANDARD_FL_FR_SW",
    ]


def test_a_network_mode_is_refused(crossover_client: TestClient) -> None:
    response = crossover_client.put(
        "/api/device/crossover/speaker-mode", json={"speaker_mode": "NETWORK_HL_HR_ML_MR_SW"}
    )

    assert response.status_code == 422
