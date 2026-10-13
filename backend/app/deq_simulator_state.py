"""The state a developer can change while the simulated DEQ runs.

The simulator and its console are two processes. The backend holds the
simulated unit, and `scripts/deq_console.py` changes what that unit reports.
The two share a file. The console writes it, and the simulator reads it again
before each reply. So a change shows up in the next frame, with nothing to
restart.

This module is development tooling, and no model of the DEQ's protocol.
`app/testing/fake_deq.py` is that model, and this module only sets its fields.
Nothing here reaches hardware.

Every field is something a real DEQ-S1000A2 reports or did. This module has no
"audio flowing" field, on purpose. Audio is a separate USB function, and the
unit never reports on it. So a switch for it would invent a field that the
protocol does not have.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

STATE_PATH_ENVIRONMENT_VARIABLE = "DEQ_SIMULATOR_STATE"
DEFAULT_STATE_PATH = Path("deq-simulator-state.json")

# The volume the car's own unit reported on 2026-10-08, so a fresh state
# starts from a real reading rather than zero.
DEFAULT_VOLUME_DB = -27

# What the unit accepts. The app's own slider runs over this range.
MINIMUM_VOLUME_DB = -80
MAXIMUM_VOLUME_DB = 10


def state_path() -> Path:
    """Returns the file the console and the simulator share."""
    from_environment = os.environ.get(STATE_PATH_ENVIRONMENT_VARIABLE)
    if from_environment:
        return Path(from_environment)
    return DEFAULT_STATE_PATH


@dataclass
class DeqSimulatorState:
    """What the simulated unit reports, and how it misbehaves.

    It holds the fields a developer may want to vary. You load it from a file
    and save it back. It depends on nothing but the standard library.
    """

    volume_db: int = DEFAULT_VOLUME_DB
    muted: bool = False
    driving: bool = False

    # Faults. Each one reproduces something a real unit can do.
    #
    # `refuses_sync` is the behaviour that cost two car sessions: the unit
    # answers an open it does not like with STATUS -5 and then goes quiet.
    refuses_sync: bool = False
    # STATUS to answer with, keyed by command id. JSON has string keys, so this
    # class stores them as strings and converts them on the way out.
    status_by_command: dict[str, int] = field(default_factory=dict)
    # Command ids to stop answering after.
    silent_after: list[int] = field(default_factory=list)
    # What 0x17 GET_SYSTEM_ERROR_FLAGS reports. Zero is no fault.
    error_flags: int = 0

    @property
    def clamped_volume_db(self) -> int:
        """The volume, held inside the range the unit accepts."""
        return max(MINIMUM_VOLUME_DB, min(MAXIMUM_VOLUME_DB, self.volume_db))

    def faults_by_command_id(self) -> dict[int, int]:
        """`status_by_command` with real integer command ids."""
        return {int(command, 0): status
                for command, status in self.status_by_command.items()}

    def describe_faults(self) -> str:
        """One line naming every fault that is on, for the console."""
        active = []
        if self.refuses_sync:
            active.append("refusing the open")
        if self.status_by_command:
            active.append(f"{len(self.status_by_command)} command faults")
        if self.silent_after:
            active.append(f"silent after {len(self.silent_after)}")
        if self.error_flags:
            active.append(f"error flags {self.error_flags:#x}")
        return ", ".join(active) if active else "none"

    def save(self, path: Path | None = None) -> None:
        """Writes the state, so the simulator picks it up on its next reply.

        The write is atomic. The simulator may read the file at any moment, and
        a half-written file would give a parse error and not a state.
        """
        target = path or state_path()
        temporary = target.with_suffix(target.suffix + ".new")
        temporary.write_text(json.dumps(asdict(self), indent=2) + "\n")
        temporary.replace(target)


def load_state(path: Path | None = None) -> DeqSimulatorState:
    """Returns the saved state, or a default one.

    A missing file is the normal first run. For an unreadable one, this
    function returns the default. This module is a development tool, and a
    refusal to start over a bad scratch file would be the wrong trade.
    """
    target = path or state_path()
    try:
        stored = json.loads(target.read_text())
    except (OSError, ValueError):
        return DeqSimulatorState()
    known = {one.name for one in DeqSimulatorState.__dataclass_fields__.values()}
    return DeqSimulatorState(**{key: value for key, value in stored.items()
                                if key in known})
