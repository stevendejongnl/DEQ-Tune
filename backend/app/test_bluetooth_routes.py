"""Checks the Bluetooth pairing endpoints against a temporary bridge directory."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.bluetooth_pairing import REQUEST_FILE, BluetoothPairing, get_bluetooth_pairing
from app.main import app
from app.test_bluetooth_pairing import NOW, write_state


@pytest.fixture
def bluetooth_client(tmp_path):
    app.dependency_overrides[get_bluetooth_pairing] = lambda: BluetoothPairing(tmp_path, clock=lambda: NOW)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_bluetooth_pairing)


def test_reads_the_window(bluetooth_client, tmp_path):
    write_state(tmp_path, NOW + 60, ["Pixel 8"])

    assert bluetooth_client.get("/api/bluetooth").json() == {
        "supported": True,
        "pairing_open": True,
        "seconds_left": 60,
        "window_seconds": 300,
        "pair_at_car_start": True,
        "bonded_phones": ["Pixel 8"],
    }


def test_opens_a_window(bluetooth_client, tmp_path):
    write_state(tmp_path, None)

    assert bluetooth_client.post("/api/bluetooth/pairing-window").status_code == 202
    assert (tmp_path / REQUEST_FILE).exists()


def test_switches_pairing_at_car_start_off(bluetooth_client, tmp_path):
    write_state(tmp_path, None)

    body = bluetooth_client.put("/api/bluetooth/settings", json={"pair_at_car_start": False}).json()

    assert body["pair_at_car_start"] is False


def test_a_machine_with_no_bridge_answers_503_to_a_change(bluetooth_client, tmp_path):
    assert bluetooth_client.get("/api/bluetooth").json()["supported"] is False
    assert bluetooth_client.post("/api/bluetooth/pairing-window").status_code == 503
    assert bluetooth_client.put("/api/bluetooth/settings", json={"pair_at_car_start": False}).status_code == 503
    assert not (tmp_path / REQUEST_FILE).exists()
