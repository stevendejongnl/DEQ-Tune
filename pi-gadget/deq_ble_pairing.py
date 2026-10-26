"""Decides when the BLE bridge lets a new phone pair.

The bridge's characteristics need an encrypted link, so a phone must bond
with the Pi before it can reach the API. The Pi has no screen and no keys,
so it cannot show or check a passkey. It controls *when* a phone can pair
instead: only while a pairing window is open.

A window opens for PAIRING_WINDOW_SECONDS:

- when the car starts, unless the settings file turns that off. The Pi has
  its own power and stays on, so "the car starts" means a new DEQ session:
  the gadget's socket appears. The bridge's own start counts too.
- when the request file appears. The web app's "Pair a new phone" button
  writes it, and so does `./deq pi pair` over SSH.

The bridge writes the window's end and the bonded phones to the state file.
The web app reads that file.

The files live in /home/deq, beside the updater's files. The backend runs as
the user `deq` and writes the settings and the request. The bridge runs as
root and writes the state.

This module uses the standard library only. `deq_ble_bridge.py` holds the
D-Bus side and imports this module, so a test can check the rules without
BlueZ.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

DIRECTORY = Path("/home/deq")
SETTINGS_FILE = "deq-ble-settings.json"
REQUEST_FILE = "deq-ble-pairing-request"
STATE_FILE = "deq-ble-state.json"

# The gadget holds this socket only while a DEQ session is live.
SESSION_SOCKET = Path("/run/deq-accessory.sock")

PAIRING_WINDOW_SECONDS = 300


class PairingWindow:
    """Holds the end of the current pairing window.

    `open()` starts a window, and `is_open()` tells whether a phone may pair
    now. It depends on a clock that gives seconds since the epoch.
    """

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock
        self.until = 0.0

    def open(self, seconds: float = PAIRING_WINDOW_SECONDS) -> None:
        self.until = self.clock() + seconds

    def is_open(self) -> bool:
        return self.clock() < self.until

    def seconds_left(self) -> int:
        return max(0, int(self.until - self.clock() + 0.999))


class CarStartWatch:
    """Tells when a DEQ session starts, from whether its socket exists.

    You call `started()` once a tick with the socket's presence. It answers
    true on the tick where the socket appears. It depends on nothing else.
    """

    def __init__(self, session_live: bool) -> None:
        self.session_live = session_live

    def started(self, session_live: bool) -> bool:
        just_started = session_live and not self.session_live
        self.session_live = session_live
        return just_started


def pair_at_car_start(directory: Path = DIRECTORY) -> bool:
    """Tells whether a window opens when the car starts. A missing or broken
    settings file means yes, so a fresh install can pair its first phone."""
    try:
        return bool(json.loads((directory / SETTINGS_FILE).read_text()).get("pair_at_car_start", True))
    except (OSError, ValueError, AttributeError):
        return True


def take_request(directory: Path = DIRECTORY) -> bool:
    """Removes the request file and tells whether it was there."""
    try:
        (directory / REQUEST_FILE).unlink()
    except FileNotFoundError:
        return False
    return True


def build_state(window: PairingWindow, bonded_phones: list[str]) -> dict:
    return {
        "pairing_until": window.until if window.is_open() else None,
        "window_seconds": PAIRING_WINDOW_SECONDS,
        "bonded_phones": sorted(bonded_phones),
    }


def write_state(state: dict, directory: Path = DIRECTORY) -> None:
    """Replaces the state file in one step, so a reader never sees half of it."""
    path = directory / STATE_FILE
    staged = path.with_suffix(".tmp")
    staged.write_text(json.dumps(state))
    staged.chmod(0o644)
    staged.replace(path)
