#!/usr/bin/env python3
"""A console for the simulated DEQ, so a developer can change what it says.

Run the backend against the simulator, then run this beside it:

    DEQ_TRANSPORT=simulator uv run fastapi dev app/main.py
    uv run python scripts/deq_console.py

The two share a state file. This console writes it, and the simulator reads it
again before each reply. So a key press shows up in the next frame, and nothing
restarts.

Keys
    up / down       volume, 1 dB          m   mute
    left / right    volume, 5 dB          d   driving
    r               refuse the open       e   error flags
    s               go silent after 0x03  c   clear every fault
    q               quit

This script is development tooling. It talks to no hardware and knows nothing
about the Pi. It only sets fields on a simulated unit in another process.
"""

from __future__ import annotations

import curses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.deq_simulator_state import (  # noqa: E402
    MAXIMUM_VOLUME_DB,
    MINIMUM_VOLUME_DB,
    DeqSimulatorState,
    load_state,
    state_path,
)

VOLUME_STEP_DB = 1
VOLUME_COARSE_STEP_DB = 5

# A command to hang after, when a developer asks for silence. 0x03 is
# GET_VERSION: early in the connect, so the failure is easy to see.
SILENCE_AFTER_COMMAND = 0x03

# An error flag value that is clearly not zero. The real unit reported 0.
EXAMPLE_ERROR_FLAGS = 0x81


def change_volume(state: DeqSimulatorState, change_db: int) -> None:
    """Moves the volume, inside the range the unit accepts."""
    state.volume_db = max(
        MINIMUM_VOLUME_DB, min(MAXIMUM_VOLUME_DB, state.volume_db + change_db)
    )


def clear_faults(state: DeqSimulatorState) -> None:
    """Turns every fault off, so the unit answers normally again."""
    state.refuses_sync = False
    state.status_by_command = {}
    state.silent_after = []
    state.error_flags = 0


def toggle_silence(state: DeqSimulatorState) -> None:
    """Turns the "stop answering" fault on or off."""
    if state.silent_after:
        state.silent_after = []
    else:
        state.silent_after = [SILENCE_AFTER_COMMAND]


def toggle_error_flags(state: DeqSimulatorState) -> None:
    """Turns the reported system error flags on or off."""
    state.error_flags = 0 if state.error_flags else EXAMPLE_ERROR_FLAGS


def apply_key(state: DeqSimulatorState, key: int) -> bool:
    """Applies one key press. Returns False when the user asked to quit.

    A dispatcher: every branch picks one named change and nothing else.
    """
    if key in (ord("q"), 27):
        return False
    if key == curses.KEY_UP:
        change_volume(state, VOLUME_STEP_DB)
    elif key == curses.KEY_DOWN:
        change_volume(state, -VOLUME_STEP_DB)
    elif key == curses.KEY_RIGHT:
        change_volume(state, VOLUME_COARSE_STEP_DB)
    elif key == curses.KEY_LEFT:
        change_volume(state, -VOLUME_COARSE_STEP_DB)
    elif key == ord("m"):
        state.muted = not state.muted
    elif key == ord("d"):
        state.driving = not state.driving
    elif key == ord("r"):
        state.refuses_sync = not state.refuses_sync
    elif key == ord("s"):
        toggle_silence(state)
    elif key == ord("e"):
        toggle_error_flags(state)
    elif key == ord("c"):
        clear_faults(state)
    return True


def checkbox(is_on: bool) -> str:
    return "[x]" if is_on else "[ ]"


def state_lines(state: DeqSimulatorState, path: Path) -> list[str]:
    """The screen, as lines. Separated from curses so a test can read it."""
    return [
        "  simulated DEQ-S1000A2",
        "",
        f"  volume        {state.volume_db:>4} dB",
        f"  {checkbox(state.muted)} muted",
        f"  {checkbox(state.driving)} driving",
        "",
        "  faults",
        f"  {checkbox(state.refuses_sync)} refuse the open (STATUS -5, then silence)",
        f"  {checkbox(bool(state.silent_after))} go silent after "
        f"{SILENCE_AFTER_COMMAND:#04x}",
        f"  {checkbox(bool(state.error_flags))} system error flags "
        f"{state.error_flags:#x}",
        "",
        f"  active: {state.describe_faults()}",
        "",
        "  up/down 1 dB   left/right 5 dB   m mute   d driving",
        "  r refuse   s silent   e errors   c clear faults   q quit",
        "",
        f"  state file: {path}",
    ]


def draw(screen, state: DeqSimulatorState, path: Path) -> None:
    screen.erase()
    for row, line in enumerate(state_lines(state, path)):
        try:
            screen.addstr(row, 0, line)
        except curses.error:
            # The window is smaller than the text. Draw what fits.
            break
    screen.refresh()


def run(screen) -> None:
    curses.curs_set(0)
    screen.keypad(True)
    path = state_path()
    state = load_state(path)
    state.save(path)
    while True:
        draw(screen, state, path)
        key = screen.getch()
        if not apply_key(state, key):
            return
        state.save(path)


def main() -> int:
    curses.wrapper(run)
    print(f"state left in {state_path()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
