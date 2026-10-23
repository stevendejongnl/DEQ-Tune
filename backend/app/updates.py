"""The app's view of the Pi's release updater.

`pi-gadget/deq_updater.py` runs as root from a timer. It writes what it
found to a state file. This module reads that file for the app, and writes
the two files the updater reads back: the settings (automatic updates on or
off) and the request for one update now.

The files live in one directory, `/home/deq` on the Pi. A machine with no
updater, such as a laptop, has no state file, and `read()` says so with
`supported=False`.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DIRECTORY = Path(os.environ.get("DEQ_UPDATE_DIRECTORY", "/home/deq"))
STATE_FILE = "deq-update-state.json"
SETTINGS_FILE = "deq-update-settings.json"
REQUEST_FILE = "deq-update-request"

# Starts the updater at once, so an Update button does not wait for the
# next timer run. One sudoers rule allows exactly this command. Without
# the rule the request file still waits for the timer.
START_UPDATER = ["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", "deq-updater.service"]

RunCommand = Callable[[list[str]], int]


def run_quietly(command: list[str]) -> int:
    try:
        return subprocess.run(command, capture_output=True, timeout=10).returncode
    except (OSError, subprocess.TimeoutExpired):
        return 1


@dataclass(frozen=True)
class UpdateHistoryEntry:
    from_version: str
    to_version: str
    at: str


@dataclass(frozen=True)
class UpdateStatus:
    """What the updater last found, and whether it runs here at all."""

    supported: bool
    installed: str | None = None
    latest: str | None = None
    automatic: bool = True
    update_available: bool = False
    gadget_pending: bool = False
    notes: str = ""
    release_url: str = ""
    checked_at: str = ""
    last_result: str = ""
    history: list[UpdateHistoryEntry] = field(default_factory=list)


class ReleaseUpdates:
    """Reads the updater's state and writes its settings and requests.

    You call `read()`, `set_automatic()` and `request_update()`. It depends
    on one directory and on a command runner, which a test replaces.
    """

    def __init__(self, directory: Path = DEFAULT_DIRECTORY, run_command: RunCommand = run_quietly) -> None:
        self.directory = directory
        self.run_command = run_command

    def read(self) -> UpdateStatus:
        state_path = self.directory / STATE_FILE
        if not state_path.exists():
            return UpdateStatus(supported=False)
        try:
            state = json.loads(state_path.read_text())
        except (OSError, json.JSONDecodeError):
            return UpdateStatus(supported=False)
        return UpdateStatus(
            supported=True,
            installed=state.get("installed"),
            latest=state.get("latest"),
            # The settings file is the truth for this switch. The state file
            # only repeats it as of the last run.
            automatic=self.automatic(),
            update_available=bool(state.get("update_available")),
            gadget_pending=bool(state.get("gadget_pending")),
            notes=state.get("notes") or "",
            release_url=state.get("release_url") or "",
            checked_at=state.get("checked_at") or "",
            last_result=state.get("last_result") or "",
            history=[
                UpdateHistoryEntry(
                    from_version=entry.get("from", ""),
                    to_version=entry.get("to", ""),
                    at=entry.get("at", ""),
                )
                for entry in state.get("history", [])
            ],
        )

    def automatic(self) -> bool:
        settings_path = self.directory / SETTINGS_FILE
        if not settings_path.exists():
            return True
        try:
            return bool(json.loads(settings_path.read_text()).get("automatic", True))
        except (OSError, json.JSONDecodeError, AttributeError):
            return True

    def set_automatic(self, automatic: bool) -> UpdateStatus:
        (self.directory / SETTINGS_FILE).write_text(json.dumps({"automatic": automatic}))
        return self.read()

    def request_update(self) -> None:
        """Asks for one update now, also while automatic updates are off."""
        (self.directory / REQUEST_FILE).write_text("")
        self.run_command(START_UPDATER)


release_updates = ReleaseUpdates()


def get_release_updates() -> ReleaseUpdates:
    """The route dependency. A test overrides it with a temporary directory."""
    return release_updates
