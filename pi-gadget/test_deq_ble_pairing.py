"""Checks when the BLE bridge lets a phone pair."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deq_ble_pairing import (  # noqa: E402
    PAIRING_WINDOW_SECONDS,
    CarStartWatch,
    REQUEST_FILE,
    SETTINGS_FILE,
    STATE_FILE,
    PairingWindow,
    build_state,
    pair_at_car_start,
    take_request,
    write_state,
)


class SettableClock:
    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    def __call__(self) -> float:
        return self.seconds


def test_a_window_is_closed_until_something_opens_it():
    window = PairingWindow(SettableClock(1000.0))

    assert not window.is_open()
    assert window.seconds_left() == 0


def test_an_open_window_closes_after_its_time():
    clock = SettableClock(1000.0)
    window = PairingWindow(clock)

    window.open()
    clock.seconds = 1000.0 + PAIRING_WINDOW_SECONDS - 1
    assert window.is_open()
    assert window.seconds_left() == 1

    clock.seconds = 1000.0 + PAIRING_WINDOW_SECONDS
    assert not window.is_open()


def test_pairing_at_car_start_is_on_without_a_settings_file(tmp_path):
    assert pair_at_car_start(tmp_path)


def test_the_settings_file_can_switch_pairing_at_car_start_off(tmp_path):
    (tmp_path / SETTINGS_FILE).write_text(json.dumps({"pair_at_car_start": False}))

    assert not pair_at_car_start(tmp_path)


def test_a_broken_settings_file_keeps_pairing_at_car_start_on(tmp_path):
    (tmp_path / SETTINGS_FILE).write_text("not json")

    assert pair_at_car_start(tmp_path)


def test_a_request_is_taken_once(tmp_path):
    (tmp_path / REQUEST_FILE).write_text("")

    assert take_request(tmp_path)
    assert not take_request(tmp_path)


def test_the_state_names_the_window_end_only_while_it_is_open(tmp_path):
    clock = SettableClock(1000.0)
    window = PairingWindow(clock)
    window.open()

    write_state(build_state(window, ["Pixel 8", "Galaxy"]), tmp_path)
    state = json.loads((tmp_path / STATE_FILE).read_text())
    assert state == {
        "pairing_until": 1000.0 + PAIRING_WINDOW_SECONDS,
        "window_seconds": PAIRING_WINDOW_SECONDS,
        "bonded_phones": ["Galaxy", "Pixel 8"],
    }

    clock.seconds = 1000.0 + PAIRING_WINDOW_SECONDS
    assert build_state(window, [])["pairing_until"] is None


def test_a_car_start_is_the_tick_where_the_session_appears():
    watch = CarStartWatch(session_live=False)

    assert not watch.started(False)
    assert watch.started(True)
    assert not watch.started(True)
    assert not watch.started(False)
    assert watch.started(True)


def test_a_session_that_was_live_when_the_bridge_started_is_no_car_start():
    watch = CarStartWatch(session_live=True)

    assert not watch.started(True)
