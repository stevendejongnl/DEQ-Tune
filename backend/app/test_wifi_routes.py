"""Checks the Wi-Fi endpoints against a fake helper."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.testing.fake_wifi_helper import FakeWifiHelper
from app.wifi_networks import WifiNetworks, get_wifi_networks


@pytest.fixture
def helper():
    return FakeWifiHelper(
        saved={"CloudSuite": True},
        visible=[{"ssid": "CloudSuite", "signal": 79, "secured": True}],
    )


@pytest.fixture
def wifi_client(helper):
    app.dependency_overrides[get_wifi_networks] = lambda: WifiNetworks(run_command=helper)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_wifi_networks)


def test_lists_the_saved_and_the_visible_networks(wifi_client):
    body = wifi_client.get("/api/wifi").json()

    assert body == {
        "saved": [{"ssid": "CloudSuite", "connected": True}],
        "visible": [{"ssid": "CloudSuite", "signal": 79, "secured": True}],
    }


def test_saves_a_network_and_answers_with_the_new_list(wifi_client, helper):
    response = wifi_client.post("/api/wifi/networks", json={"ssid": "Home", "password": "secret-password"})

    assert response.status_code == 200
    assert [network["ssid"] for network in response.json()["saved"]] == ["CloudSuite", "Home"]
    assert helper.passwords == ["secret-password"]


@pytest.mark.parametrize(
    "body",
    [
        {"ssid": "", "password": "secret-password"},
        {"ssid": "x" * 33, "password": "secret-password"},
        {"ssid": "Home\n", "password": "secret-password"},
        {"ssid": "Home", "password": "short"},
        {"ssid": "Home", "password": "x" * 64},
    ],
)
def test_refuses_a_bad_network_before_the_helper_runs(wifi_client, helper, body):
    response = wifi_client.post("/api/wifi/networks", json=body)

    assert response.status_code == 422
    assert helper.passwords == []


def test_saves_an_open_network_and_a_hex_key(wifi_client, helper):
    wifi_client.post("/api/wifi/networks", json={"ssid": "Open"})
    wifi_client.post("/api/wifi/networks", json={"ssid": "Hex", "password": "a1" * 32})

    assert helper.passwords == ["", "a1" * 32]


def test_forgets_a_network(wifi_client, helper):
    helper.saved["Home"] = False

    response = wifi_client.post("/api/wifi/forget", json={"ssid": "Home"})

    assert [network["ssid"] for network in response.json()["saved"]] == ["CloudSuite"]


def test_a_refusal_is_a_conflict_with_the_reason(wifi_client, helper):
    helper.deq_session_running = True

    response = wifi_client.post("/api/wifi/forget", json={"ssid": "CloudSuite"})

    assert response.status_code == 409
    assert "DEQ is connected" in response.json()["detail"]


def test_asks_the_bridge_to_join(wifi_client, helper):
    response = wifi_client.post("/api/wifi/join")

    assert response.status_code == 202
    assert helper.join_requests == 1


def test_a_machine_with_no_helper_answers_503():
    def missing_sudo(command, **options):
        raise FileNotFoundError("sudo")

    app.dependency_overrides[get_wifi_networks] = lambda: WifiNetworks(run_command=missing_sudo)
    try:
        with TestClient(app) as client:
            assert client.get("/api/wifi").status_code == 503
    finally:
        app.dependency_overrides.pop(get_wifi_networks)
