"""A simulated DEQ whose answers a developer can change while it runs.

`DEQ_TRANSPORT=simulator` serves this unit in place of a real one. So the whole
app runs with no hardware. A person can still see what happens when the volume
moves, the unit mutes, or a command fails.

It is `FakeDeq` plus a state file. `FakeDeq` holds every protocol rule,
measured from real traffic. This class only copies the current state onto it
before each reply. The split matters: the protocol rules stay pinned to
captures, and the knobs stay out of them.

`DEQ_TRANSPORT=fake` still exists, and the tests use it. It takes its state
from its constructor and reads no file, so a test stays hermetic.
"""

from __future__ import annotations

from pathlib import Path

from app.deq_simulator_state import DeqSimulatorState, load_state
from app.deq_transport import Transport
from app.testing.fake_deq import FakeDeq


class DeqSimulator(Transport):
    """A fake DEQ that reads its state from a file again before each reply.

    It answers frames the way `FakeDeq` does. You use it through the
    `Transport` seam like any other link. It depends on `FakeDeq` for the
    protocol, and on a state file for what to report.
    """

    def __init__(self, state_path: Path | None = None,
                 load_state_function=load_state) -> None:
        self.state_path = state_path
        self.load_state_function = load_state_function
        self.unit = FakeDeq()

    def send_frame(self, frame: bytes) -> None:
        self.apply_state(self.load_state_function(self.state_path))
        self.unit.send_frame(frame)

    def receive_frame(self, timeout_seconds: float) -> bytes:
        return self.unit.receive_frame(timeout_seconds)

    def close(self) -> None:
        self.unit.close()

    def apply_state(self, state: DeqSimulatorState) -> None:
        """Copies the state a developer set onto the simulated unit."""
        self.unit.volume_db = state.clamped_volume_db
        self.unit.muted = state.muted
        self.unit.driving = state.driving
        self.unit.refuses_sync = state.refuses_sync
        self.unit.status_by_command = state.faults_by_command_id()
        self.unit.silent_after = set(state.silent_after)
        self.unit.error_flags = state.error_flags
        # A unit told to answer again must forget that it went quiet,
        # otherwise clearing a fault in the console leaves it mute.
        if not state.silent_after and not state.refuses_sync:
            self.unit.answers = True
