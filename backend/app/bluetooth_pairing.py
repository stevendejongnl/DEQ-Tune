"""The app's view of the BLE bridge's pairing window.

`pi-gadget/deq_ble_bridge.py` runs as root and lets a new phone bond only
while a pairing window is open. It writes the window and the bonded phones
to a state file. This module reads that file for the app, and writes the
two files the bridge reads back: the settings (a window at each car start, on
or off) and the request for one window now.

The files live in `/home/deq` on the Pi. A machine with no bridge, such as
a laptop, has no state file, and `read()` says so with `supported=False`.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DIRECTORY = Path(os.environ.get("DEQ_BLE_DIRECTORY", "/home/deq"))
STATE_FILE = "deq-ble-state.json"
SETTINGS_FILE = "deq-ble-settings.json"
REQUEST_FILE = "deq-ble-pairing-request"


@dataclass(frozen=True)
class PairingStatus:
    """The pairing window now, and whether a bridge runs here at all."""

    supported: bool
    pairing_open: bool = False
    seconds_left: int = 0
    window_seconds: int = 0
    pair_at_car_start: bool = True
    bonded_phones: list[str] = field(default_factory=list)


class BluetoothPairing:
    """Reads the bridge's pairing state and writes its settings and requests.

    You call `read()`, `set_pair_at_car_start()` and `request_window()`. It
    depends on one directory and on a clock that gives seconds since the
    epoch, which a test replaces.
    """

    def __init__(self, directory: Path = DEFAULT_DIRECTORY, clock: Callable[[], float] = time.time) -> None:
        self.directory = directory
        self.clock = clock

    def read(self) -> PairingStatus:
        try:
            state = json.loads((self.directory / STATE_FILE).read_text())
        except (OSError, json.JSONDecodeError):
            return PairingStatus(supported=False)
        pairing_until = state.get("pairing_until")
        seconds_left = 0 if pairing_until is None else max(0, int(pairing_until - self.clock() + 0.999))
        return PairingStatus(
            supported=True,
            pairing_open=seconds_left > 0,
            seconds_left=seconds_left,
            window_seconds=int(state.get("window_seconds") or 0),
            pair_at_car_start=self.pair_at_car_start(),
            bonded_phones=[str(name) for name in state.get("bonded_phones", [])],
        )

    def pair_at_car_start(self) -> bool:
        try:
            return bool(json.loads((self.directory / SETTINGS_FILE).read_text()).get("pair_at_car_start", True))
        except (OSError, json.JSONDecodeError, AttributeError):
            return True

    def set_pair_at_car_start(self, pair_at_car_start: bool) -> PairingStatus:
        (self.directory / SETTINGS_FILE).write_text(json.dumps({"pair_at_car_start": pair_at_car_start}))
        return self.read()

    def request_window(self) -> None:
        """Asks the bridge to open a window. It takes the request within a second."""
        (self.directory / REQUEST_FILE).write_text("")


bluetooth_pairing = BluetoothPairing()


def get_bluetooth_pairing() -> BluetoothPairing:
    """The route dependency. A test overrides it with a temporary directory."""
    return bluetooth_pairing
