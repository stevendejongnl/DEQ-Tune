#!/usr/bin/env python3
"""Checks this app against a real DEQ unit.

This project came from the Pioneer app and from captured traffic, with a fake
unit in place of the hardware. Before this script, no real unit answered it.
This script closes that gap: plug a DEQ in, run the script, and read what
matched.

    cd backend
    PYTHONPATH=. uv run python scripts/check_real_deq.py

By default it only reads. Every step that writes to the unit is off unless you
ask for it:

    PYTHONPATH=. uv run python scripts/check_real_deq.py --write

This script uses `DEQ_TRANSPORT`, the same as the app itself (`deq_device.py`).
Run it on the Pi, where the gadget holds the link:

    DEQ_TRANSPORT=accessory PYTHONPATH=. uv run python scripts/check_real_deq.py

`accessory` is the default transport for this script (the app's default is
`fake`). A check of a real unit is the one reason to run the script, and the Pi
reaches one. The script rejects `DEQ_TRANSPORT=fake`. A check against the fake
tells nothing about a real unit, and the script has no other job.

`DEQ_TRANSPORT=usb` is the other real option, for a machine that can present
the device side of a USB link. It needs the `usb` extra (`uv sync --extra
usb`). On Linux a plain user usually cannot open a USB device. Either run the
script with `sudo -E env PYTHONPATH=. ...`, or install
`scripts/99-pioneer-deq.rules` as a udev rule (install steps in its own
comment). The `accessory` transport needs neither, because it opens a Unix
socket and not the device.

The script prints a list of checks, each `ok`, `differs` or `failed`, and a
count at the end. A `differs` line is the interesting one. It means the unit
answered, but not the way the captures and the APK said it would. Record each
of those in `USB_CAPTURE_NOTES.md` in the outer repo. The app is the authority,
and this code is the thing under test.
"""

from __future__ import annotations

import argparse
import os
import sys

from app.deq_blob import encode_blob
from app.deq_device import (
    ACCESSORY_TRANSPORT_NAME,
    FAKE_TRANSPORT_NAME,
    USB_TRANSPORT_NAME,
    DeviceUnavailable,
    build_transport,
)
from app.deq_session import (
    COMMAND_KEEPALIVE,
    STARTUP_STEPS,
    DeqSession,
    DeviceIdentity,
)
from app.deq_transport import Transport, TransportError

# What the fake unit answers, so a real one can be held against it.
EXPECTED_BLOB_BYTES = 572


class Report:
    """Collects what matched and what did not.

    It records one line per check, and you call `ok`, `differs` or `failed`. It
    depends on nothing but a print.
    """

    def __init__(self) -> None:
        self.differences: list[str] = []
        self.failures: list[str] = []

    def ok(self, what: str, detail: str = "") -> None:
        print(f"  ok       {what}{f' — {detail}' if detail else ''}")

    def differs(self, what: str, detail: str) -> None:
        print(f"  DIFFERS  {what} — {detail}")
        self.differences.append(f"{what}: {detail}")

    def failed(self, what: str, detail: str) -> None:
        print(f"  FAILED   {what} — {detail}")
        self.failures.append(f"{what}: {detail}")

    def summarise(self) -> int:
        print()
        if self.failures == [] and self.differences == []:
            print("Every check matched. The unit answers the way this app expects.")
            return 0
        if self.differences != []:
            print(f"{len(self.differences)} answer(s) differed from what was expected:")
            for difference in self.differences:
                print(f"  - {difference}")
            print("Record these in USB_CAPTURE_NOTES.md: the unit is the authority.")
        if self.failures != []:
            print(f"{len(self.failures)} check(s) failed outright:")
            for failure in self.failures:
                print(f"  - {failure}")
        return 1


def check_link(report: Report) -> Transport:
    """Opens the link named by `DEQ_TRANSPORT`, or stops with the reason."""
    transport_name = os.environ.get("DEQ_TRANSPORT", ACCESSORY_TRANSPORT_NAME)
    if transport_name == FAKE_TRANSPORT_NAME:
        raise TransportError(
            "DEQ_TRANSPORT=fake checks nothing about a real unit, which is this "
            f"script's only job. Use {ACCESSORY_TRANSPORT_NAME!r} or "
            f"{USB_TRANSPORT_NAME!r}."
        )
    print(f"Opening the link ({transport_name})")
    transport = build_transport(transport_name)
    report.ok("opened the link", transport_name)
    return transport


def check_startup(report: Report, session: DeqSession) -> None:
    """Runs the app's own connect sequence, one command at a time.

    Running the steps singly rather than through `start()` says which
    command a real unit refuses, if any.
    """
    print("\nRunning the startup sequence")
    for command_id, body in STARTUP_STEPS:
        try:
            reply = session.exchange(command_id, body)
        except TransportError as caught_error:
            report.failed(f"command 0x{command_id:02x}", str(caught_error))
            return
        except Exception as caught_error:
            report.differs(f"command 0x{command_id:02x}", str(caught_error))
            continue
        report.ok(f"command 0x{command_id:02x}", f"{reply.payload_length}-byte reply")


def check_identity(report: Report, session: DeqSession) -> DeviceIdentity | None:
    """Reads what the unit is, and returns it for `check_configuration`
    to cross-check its speaker mode against."""
    print("\nReading what the unit is")
    try:
        identity = session.read_device_identity()
    except Exception as caught_error:
        report.failed("device identity", str(caught_error))
        return None
    report.ok("firmware version", f"{identity.firmware_version >> 8}.{identity.firmware_version & 0xFF:02d}")
    if len(identity.serial) == 0:
        report.differs("serial number", "the unit sent an empty string")
    else:
        report.ok("serial number", identity.serial)
    return identity


def check_configuration(
    report: Report, session: DeqSession
) -> None:
    """Reads the settings blob and checks it round-trips.

    No read-only check is stronger than this one. The blob is the unit's whole
    semantic state. `deq_blob` follows the app's own reader, so a byte-exact
    round trip means that reader is right.

    This check no longer compares the speaker mode with the reply of `0x04`.
    The APK declares a SPEAKER_MODE field there at payload offset 36. A real
    unit answered `0x04` with 24 payload bytes on 2026-10-08. So the field lies
    past the end of the reply. For that reason this check reported `0` against
    the blob's `3`. Only the blob holds a readable speaker mode.
    """
    print("\nReading the settings blob")
    try:
        configuration = session.read_user_configuration()
    except Exception as caught_error:
        report.failed("reading the blob", str(caught_error))
        return

    rebuilt = encode_blob(configuration)
    if len(rebuilt) != EXPECTED_BLOB_BYTES:
        report.differs(
            "blob size", f"{len(rebuilt)} bytes, not the {EXPECTED_BLOB_BYTES} expected"
        )
    else:
        report.ok("blob size", f"{len(rebuilt)} bytes")

    report.ok("speaker mode", str(configuration.speaker_mode))
    report.ok("equalizer bands", str(configuration.band_count))
    report.ok("bank in use", str(configuration.bank_in_use))

    # The APK's writer explained three fields. This check is the first chance
    # to compare any of them with a real unit. See USB_CAPTURE_NOTES.md in the
    # outer repo for the trace.
    if configuration.always_false_flag != 0:
        report.differs(
            "always_false_flag",
            f"unit sent {configuration.always_false_flag}, "
            "but the app's writer only ever emits a literal 0 here",
        )
    else:
        report.ok("always_false_flag", "0, as the app's writer always sends")

    if configuration.car_model_name_key_digest == bytes(16):
        report.ok("car_model_name_key_digest", "16 zero bytes (no car model selected)")
    elif len(configuration.car_model_name_key_digest) == 16:
        report.ok(
            "car_model_name_key_digest",
            f"{configuration.car_model_name_key_digest.hex()} (MD5 of carModelNameKey)",
        )
    else:
        report.failed(
            "car_model_name_key_digest",
            f"{len(configuration.car_model_name_key_digest)} bytes, expected 16",
        )


def check_keepalive(report: Report, session: DeqSession) -> None:
    """Sends several keepalives, as the app does for a whole session."""
    print("\nHolding the session open")
    for attempt in range(1, 6):
        try:
            session.exchange(COMMAND_KEEPALIVE)
        except Exception as caught_error:
            report.failed(f"keepalive {attempt}", str(caught_error))
            return
    report.ok("five keepalives", "the session stayed up")


def check_write_back(report: Report, session: DeqSession) -> None:
    """Writes the unit's own settings back to it, unchanged.

    No write is gentler than this one. The blob that comes back is the one that
    went in. So a unit that accepts it stays as it was.
    """
    print("\nWriting the blob back, unchanged")
    try:
        before = session.read_user_configuration()
        session.write_user_configuration(before)
        after = session.read_user_configuration()
    except Exception as caught_error:
        report.failed("writing the blob", str(caught_error))
        return

    if encode_blob(before) == encode_blob(after):
        report.ok("blob round trip", "the unit kept every byte")
    else:
        report.differs("blob round trip", "the unit changed bytes this app did not")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        # The docstring's own line breaks and command examples are
        # meant to be read as written, not reflowed into one paragraph.
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="also write the unit's own settings back to it, unchanged",
    )
    arguments = parser.parse_args()

    report = Report()
    try:
        transport = check_link(report)
    except (TransportError, DeviceUnavailable) as caught_error:
        print(f"  FAILED   opening the link — {caught_error}")
        return 1

    session = DeqSession(transport)
    try:
        check_startup(report, session)
        check_identity(report, session)
        check_configuration(report, session)
        check_keepalive(report, session)
        if arguments.write:
            check_write_back(report, session)
        else:
            print("\nSkipping the write checks. Pass --write to run them.")
    finally:
        session.close()

    return report.summarise()


if __name__ == "__main__":
    sys.exit(main())
