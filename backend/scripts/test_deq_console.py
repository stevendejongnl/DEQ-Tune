"""Tests for the simulated DEQ's console.

These tests cover only the pure parts: which key makes which change, and what
the screen says. Curses does the drawing, and the tests leave that to it.
"""

from __future__ import annotations

import curses
from pathlib import Path

from app.deq_simulator_state import (
    MAXIMUM_VOLUME_DB,
    MINIMUM_VOLUME_DB,
    DeqSimulatorState,
)

from scripts.deq_console import SILENCE_AFTER_COMMAND, apply_key, state_lines


def test_the_arrow_keys_move_the_volume():
    state = DeqSimulatorState(volume_db=-27)
    apply_key(state, curses.KEY_UP)
    assert state.volume_db == -26
    apply_key(state, curses.KEY_DOWN)
    assert state.volume_db == -27
    apply_key(state, curses.KEY_RIGHT)
    assert state.volume_db == -22
    apply_key(state, curses.KEY_LEFT)
    assert state.volume_db == -27


def test_the_volume_stops_at_the_limits_the_unit_accepts():
    state = DeqSimulatorState(volume_db=MAXIMUM_VOLUME_DB)
    apply_key(state, curses.KEY_UP)
    assert state.volume_db == MAXIMUM_VOLUME_DB
    state.volume_db = MINIMUM_VOLUME_DB
    apply_key(state, curses.KEY_DOWN)
    assert state.volume_db == MINIMUM_VOLUME_DB


def test_m_and_d_toggle_mute_and_driving():
    state = DeqSimulatorState()
    apply_key(state, ord("m"))
    apply_key(state, ord("d"))
    assert state.muted is True
    assert state.driving is True
    apply_key(state, ord("m"))
    assert state.muted is False


def test_r_toggles_the_refused_open():
    state = DeqSimulatorState()
    apply_key(state, ord("r"))
    assert state.refuses_sync is True
    apply_key(state, ord("r"))
    assert state.refuses_sync is False


def test_s_toggles_going_silent():
    state = DeqSimulatorState()
    apply_key(state, ord("s"))
    assert state.silent_after == [SILENCE_AFTER_COMMAND]
    apply_key(state, ord("s"))
    assert state.silent_after == []


def test_e_toggles_the_error_flags():
    state = DeqSimulatorState()
    apply_key(state, ord("e"))
    assert state.error_flags != 0
    apply_key(state, ord("e"))
    assert state.error_flags == 0


def test_c_clears_every_fault_and_leaves_the_device_state_alone():
    state = DeqSimulatorState(
        volume_db=-5, muted=True, refuses_sync=True,
        status_by_command={"0x03": -7}, silent_after=[4], error_flags=0x81,
    )
    apply_key(state, ord("c"))
    assert state.refuses_sync is False
    assert state.status_by_command == {}
    assert state.silent_after == []
    assert state.error_flags == 0
    # Clearing faults is not a reset: the volume and mute are not faults.
    assert state.volume_db == -5
    assert state.muted is True


def test_q_asks_to_quit_and_every_other_key_does_not():
    assert apply_key(DeqSimulatorState(), ord("q")) is False
    assert apply_key(DeqSimulatorState(), ord("m")) is True


def test_an_unknown_key_changes_nothing():
    state = DeqSimulatorState()
    assert apply_key(state, ord("z")) is True
    assert state == DeqSimulatorState()


def test_the_screen_shows_the_volume_and_which_faults_are_on():
    lines = "\n".join(state_lines(
        DeqSimulatorState(volume_db=-12, muted=True, refuses_sync=True),
        Path("somewhere/state.json"),
    ))
    assert "-12 dB" in lines
    assert "[x] muted" in lines
    assert "[x] refuse the open" in lines
    assert "[ ] driving" in lines
    assert "somewhere/state.json" in lines
