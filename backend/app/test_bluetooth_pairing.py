"""Checks the app's view of the BLE bridge's pairing window."""

from __future__ import annotations

import json

from app.bluetooth_pairing import REQUEST_FILE, SETTINGS_FILE, STATE_FILE, BluetoothPairing

NOW = 1_793_000_000.0


def write_state(directory, pairing_until, bonded_phones=()) -> None:
    (directory / STATE_FILE).write_text(
        json.dumps({"pairing_until": pairing_until, "window_seconds": 300, "bonded_phones": list(bonded_phones)})
    )


def test_a_machine_with_no_bridge_is_not_supported(tmp_path):
    assert BluetoothPairing(tmp_path, clock=lambda: NOW).read().supported is False


def test_an_open_window_reports_its_seconds_left(tmp_path):
    write_state(tmp_path, NOW + 120.5, ["Pixel 8"])

    status = BluetoothPairing(tmp_path, clock=lambda: NOW).read()

    assert status.supported is True
    assert status.pairing_open is True
    assert status.seconds_left == 121
    assert status.window_seconds == 300
    assert status.bonded_phones == ["Pixel 8"]


def test_a_window_whose_end_has_passed_is_closed(tmp_path):
    # The bridge rewrites the file each second, but a reader can come
    # between the end and the next rewrite.
    write_state(tmp_path, NOW - 1)

    status = BluetoothPairing(tmp_path, clock=lambda: NOW).read()

    assert status.pairing_open is False
    assert status.seconds_left == 0


def test_pairing_at_car_start_is_on_until_switched_off(tmp_path):
    write_state(tmp_path, None)
    pairing = BluetoothPairing(tmp_path, clock=lambda: NOW)
    assert pairing.read().pair_at_car_start is True

    status = pairing.set_pair_at_car_start(False)

    assert status.pair_at_car_start is False
    assert json.loads((tmp_path / SETTINGS_FILE).read_text()) == {"pair_at_car_start": False}


def test_a_window_request_writes_the_request_file(tmp_path):
    BluetoothPairing(tmp_path, clock=lambda: NOW).request_window()

    assert (tmp_path / REQUEST_FILE).exists()
