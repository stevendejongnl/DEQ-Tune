#!/usr/bin/env python3
"""Asks a real DEQ to play the audio this device writes.

**It did its job: a person heard mode 5 in a car on 2026-10-08.** The
DEQ plays what this device writes once it holds `SP_OTHER_SOURCE`.
THROUGH plays the car's own audio with the same gadget attached. The
rest of the table is still open for this script. `MIX_OTHER_SOURCE` (6)
comes first: the session ended before it got there. It would say whether
our audio and the car's can play together.

It sends one source mode at a time and gives a person time to listen. Only a
listener can read the answer. The unit accepts every mode with STATUS 0,
whether or not anything comes out of the speakers.

    cd backend
    DEQ_TRANSPORT=accessory PYTHONPATH=. uv run python \\
        scripts/probe_audio_output.py

Run it on the Pi, where the gadget holds the link. Feed audio first: set
`FEED_AUDIO = True` and `AUDIO_FEED_TONE_HZ = 440` in
`pi-gadget/deq_accessory.py`, deploy, and start the gadget. Without a tone the
unit has nothing to play, and every mode sounds the same.

**It writes to the unit.** Each step sends a source mode, a PLAY_READY
notification and a volume. When the script finishes, it puts back the
mode and the volume it found, also after a Ctrl-C. It sends nothing
outside what the real app sends in its own cold start.

Rehearse it against the fake unit before the car, where it costs nothing:

    DEQ_TRANSPORT=fake PYTHONPATH=. uv run python \\
        scripts/probe_audio_output.py --hold-seconds 0
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from app.deq_device import (
    ACCESSORY_TRANSPORT_NAME,
    DeviceUnavailable,
    build_transport,
)
from app.deq_session import DeqSession
from app.deq_enums import AUDIO_SOURCE
from app.deq_transport import TransportError, TransportTimeout

# The modes to try, in the order the app's own code makes likely.
#
# `SourceMode.a(playing, connectionKind)` is what the app calls to pick a mode.
# On 2026-10-08 the emulator ran it for all ten modes and all three connection
# kinds, and logged the mapping. That beats a read of its packed-switch by eye.
# Over AOA, with other audio playing:
#
#   from THROUGH (4)       -> SP_OTHER_SOURCE (5)
#   from STAND_ALONE (0)   -> SP_OTHER_SOURCE (5)
#   from SP_GENUINE (1)    -> MIX_OTHER_SOURCE (6)
#   from SP_OTHER (5)      -> MIX_OTHER_SOURCE (6)
#   from MIX_GENUINE (2)   -> THROUGH (4)
#   from MIX_OTHER (6)     -> THROUGH (4)
#   from CAR_SOURCE (3)    -> THROUGH (4)
#
# The real unit sits at THROUGH, so the app would send 5, and 6 is the step
# after it. Both PURE modes return null for every connection kind, so the app
# never sends them. Pass `--modes 7,8` to try them anyway.
DEFAULT_MODE_WIRE_VALUES = (5, 6)

# How long each mode stays on, so a person can hear whether it worked.
DEFAULT_HOLD_SECONDS = 8.0

# The volume to ask for while the probe holds a mode. The unit sat at -37 dB
# through the whole car session, which is near the bottom of its range. So a
# tone at that level may be inaudible whatever the mode says. The unit refused
# this write with STATUS -6 under THROUGH. This probe also measures whether it
# refuses under an OTHER mode.
DEFAULT_VOLUME_DB = -20


class ProbeLog:
    """Prints what the unit answered, one line per step.

    It records nothing and decides nothing. You call `step`, `reply` or `note`.
    It depends on a print and on nothing else.
    """

    def step(self, what: str) -> None:
        print(f"\n{what}")

    def reply(self, what: str, detail: str) -> None:
        print(f"  {what:28s} {detail}")

    def note(self, what: str) -> None:
        print(f"  {what}")


def mode_name(wire_value: int) -> str:
    """Returns the APK's name for a source mode, or a plain number."""
    for value in AUDIO_SOURCE.values:
        if value.wire_value == wire_value:
            return value.name
    return f"wire {wire_value}"


def read_state(session: DeqSession, log: ProbeLog) -> dict[str, int]:
    """Reads the unit's mode, volume, mute state and driving state.

    All four are reads with an empty body (0x0c, 0x0e, 0x10 and 0x11). So this
    function changes nothing on the unit.
    """
    state = {
        "mode": session.read_mode(),
        "volume_db": session.read_volume(),
        "mute_state": session.read_mute_state(),
        "driving_state": session.read_driving_state(),
    }
    log.reply("mode", f"{state['mode']} ({mode_name(state['mode'])})")
    log.reply("volume", f"{state['volume_db']} dB")
    log.reply("mute state", str(state["mute_state"]))
    log.reply("driving state", str(state["driving_state"]))
    return state


def hold_one_mode(
    session: DeqSession,
    log: ProbeLog,
    wire_value: int,
    volume_db: int,
    hold_seconds: float,
    sleep_function=time.sleep,
) -> None:
    """Sets one source mode, asks for a volume, and waits.

    The order matters. The mode goes first, because under THROUGH the unit
    refused the volume write. The probe has to find out whether an OTHER mode
    accepts it. PLAY_READY follows, because the app sends it last in its own
    cold start.
    """
    log.step(f"mode {wire_value} ({mode_name(wire_value)})")
    reply = session.exchange(0x0B, wire_value.to_bytes(4, "little", signed=True))
    log.reply("0x0b SET_MODE", describe_status(reply.body))

    session.notify_play_ready()
    log.reply("0x1a PLAY_READY", "accepted")

    volume_reply = session.exchange(
        0x0D, volume_db.to_bytes(4, "little", signed=True)
    )
    log.reply(f"0x0d SET_VOLUME {volume_db}", describe_status(volume_reply.body))

    read_state(session, log)
    if hold_seconds > 0:
        log.note(f"listen now -- holding this mode for {hold_seconds:.0f}s")
        sleep_function(hold_seconds)


def describe_status(body: bytes) -> str:
    """Returns a reply's STATUS and the field that follows it, if any."""
    if len(body) < 4:
        return "no STATUS in the reply"
    status = int.from_bytes(body[0:4], "little", signed=True)
    if len(body) < 8:
        return f"STATUS {status}"
    first_field = int.from_bytes(body[4:8], "little", signed=True)
    return f"STATUS {status}, reported {first_field}"


def drain_pending_frames(transport, quiet_seconds: float = 1.5) -> int:
    """Reads and throws away whatever is already waiting on the link.

    The gadget drives the link whenever no backend holds it. So a stop of the
    backend to run this script leaves the gadget's own keepalive reply in
    flight. That reply carries a transaction id far ahead of a fresh session's.
    `DeqSession` reports it as a mismatch and not as a leftover, and that is
    right: an id ahead of the request is not stale.

    It cost a car session on 2026-10-08: "sent command 0x00, got a reply to
    0x02". A drain first fixes it. The drain belongs here and not in the
    session, which cannot tell a leftover from a fault.
    """
    discarded = 0
    while True:
        try:
            transport.receive_frame(quiet_seconds)
        except (TransportTimeout, TransportError):
            return discarded
        discarded += 1


def restore_state(
    session: DeqSession, log: ProbeLog, state: dict[str, int]
) -> None:
    """Puts back the mode and volume the unit held before the probe.

    This restore gives the car its audio back. So neither write may be skipped
    because the other failed. The mode write timed out once on 2026-10-08,
    right after a 20-second hold in mode 5, and the volume write never ran.
    This function tries each one twice and reports what happened.
    """
    log.step("putting the unit back")
    restore_one_field(
        session,
        log,
        0x0B,
        state["mode"],
        f"mode {state['mode']} ({mode_name(state['mode'])})",
    )
    restore_one_field(
        session, log, 0x0D, state["volume_db"], f"volume {state['volume_db']} dB"
    )


def restore_one_field(
    session: DeqSession,
    log: ProbeLog,
    command_id: int,
    value: int,
    what: str,
    attempts: int = 2,
) -> None:
    """Writes one value back, and tries again once if the unit stays quiet.

    This function reports a failure here and does not raise it. The next write
    still has to run. A person in a car needs to read which part of the restore
    worked.
    """
    for attempt in range(1, attempts + 1):
        try:
            reply = session.exchange(
                command_id, value.to_bytes(4, "little", signed=True)
            )
        except Exception as caught_error:
            log.reply(what, f"attempt {attempt} failed: {caught_error}")
            continue
        log.reply(what, describe_status(reply.body))
        return
    log.note(f"{what} was NOT restored. Stop the gadget to give the car its audio.")


def run_probe(
    session: DeqSession,
    log: ProbeLog,
    mode_wire_values=DEFAULT_MODE_WIRE_VALUES,
    volume_db: int = DEFAULT_VOLUME_DB,
    hold_seconds: float = DEFAULT_HOLD_SECONDS,
    sleep_function=time.sleep,
) -> dict[str, int]:
    """Runs the whole probe and returns the state it found at the start.

    The session is a parameter, so a test passes a fake unit through it and
    a car run passes the real link.
    """
    log.step("the unit's state before anything is sent")
    state_before = read_state(session, log)

    try:
        for wire_value in mode_wire_values:
            hold_one_mode(
                session,
                log,
                wire_value,
                volume_db,
                hold_seconds,
                sleep_function=sleep_function,
            )
    finally:
        restore_state(session, log, state_before)
    return state_before


def parse_arguments(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--modes",
        default=",".join(str(one) for one in DEFAULT_MODE_WIRE_VALUES),
        help="source mode wire values to try, comma separated",
    )
    parser.add_argument(
        "--volume-db",
        type=int,
        default=DEFAULT_VOLUME_DB,
        help="volume to ask for while each mode is held",
    )
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=DEFAULT_HOLD_SECONDS,
        help="how long to hold each mode, so a person can listen",
    )
    return parser.parse_args(arguments)


def main(arguments: list[str]) -> int:
    options = parse_arguments(arguments)
    transport_name = os.environ.get("DEQ_TRANSPORT", ACCESSORY_TRANSPORT_NAME)
    print(f"Opening the link ({transport_name})")
    try:
        transport = build_transport(transport_name)
    except (DeviceUnavailable, TransportError) as caught_error:
        print(f"no link: {caught_error}")
        return 1

    discarded = drain_pending_frames(transport)
    if discarded > 0:
        print(f"dropped {discarded} frame(s) left over from the gadget's own session")

    session = DeqSession(transport)
    try:
        session.start()
        run_probe(
            session,
            ProbeLog(),
            mode_wire_values=[int(one) for one in options.modes.split(",")],
            volume_db=options.volume_db,
            hold_seconds=options.hold_seconds,
        )
    except Exception as caught_error:
        print(f"\nthe probe stopped: {caught_error}")
        return 1
    finally:
        session.close()

    print("\nDone. Which mode, if any, was audible is the answer this was for.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
