#!/usr/bin/env python3
"""Plays the DEQ against the ESP gadget, from a laptop at the desk.

The DEQ is the USB host of the link, and so is a laptop. This script takes
the DEQ's side of everything up to the conversation, the way a real unit
does it:

  1. it finds the board as the tablet, 18d1:4ee7
  2. GET_PROTOCOL, and it expects version 2
  3. six identification strings and SET_AUDIO_MODE 1
  4. START, and it waits for the board to come back as 18d1:2d04
  5. it opens the accessory interface (index 2)
  6. it answers every frame the board sends with STATUS 0

So a desk run proves stages 1 to 6 of the probe, with this script in the
DEQ's place. What only the real DEQ can answer, its own replies and how
long it holds the link, needs a car session. Its strings say "laptop" and
"fake-deq-host", so the board's report tells a desk run from a car run.

It uses the backend's own codec, so it repeats no wire format. Run it with
the backend's environment:

    cd backend && uv run --extra usb python ../esp-gadget/fake_deq_host.py

It needs read and write access to the board's USB device. Android's udev
rules give that to Google's vendor id 18d1, which both identities use.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import usb.core
import usb.util

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.deq_protocol import Direction, Message, decode_frame, encode_frame  # noqa: E402

GOOGLE_VENDOR_ID = 0x18D1
TABLET_PRODUCT_ID = 0x4EE7
ACCESSORY_PRODUCT_IDS = range(0x2D00, 0x2D06)

GET_PROTOCOL = 51
SEND_STRING = 52
START = 53
SET_AUDIO_MODE = 58
AUDIO_MODE_ON = 1

VENDOR_IN = usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_IN
VENDOR_OUT = usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_OUT

# What the real DEQ sends has the shape of the app's accessory filter
# ("Pioneer", "DEQ-1000A-MZ"). These say plainly that a laptop sent them.
IDENTIFICATION_STRINGS = (
    "laptop",
    "fake-deq-host",
    "deq-tune esp-gadget desk test",
    "1",
    "https://github.com/stevendejongnl/deq-tune",
    "0000",
)

ACCESSORY_INTERFACE = 2
ACCESSORY_ENDPOINT_IN = 0x81
ACCESSORY_ENDPOINT_OUT = 0x01
READ_TIMEOUT_MS = 500
STATUS_OK = bytes(4)


def log(message: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {message}", flush=True)


def find_board(product_ids, wait_seconds: float):
    """Returns the board once it shows one of these product ids, or None."""
    give_up = time.monotonic() + wait_seconds
    while time.monotonic() < give_up:
        for device in usb.core.find(find_all=True, idVendor=GOOGLE_VENDOR_ID):
            if device.idProduct in product_ids:
                return device
        time.sleep(0.1)
    return None


def run_handshake(board) -> None:
    """Steps 2 to 4: the AOA handshake, as the DEQ sends it."""
    version = int.from_bytes(bytes(board.ctrl_transfer(VENDOR_IN, GET_PROTOCOL, 0, 0, 2)), "little")
    log(f"stage 2: GET_PROTOCOL answered {version}")
    if version != 2:
        raise SystemExit(f"the board answered AOA version {version}; the DEQ needs 2")
    for index, text in enumerate(IDENTIFICATION_STRINGS):
        board.ctrl_transfer(VENDOR_OUT, SEND_STRING, 0, index, text.encode() + b"\0")
    board.ctrl_transfer(VENDOR_OUT, SET_AUDIO_MODE, AUDIO_MODE_ON, 0, None)
    log("stage 3: six strings and SET_AUDIO_MODE 1 sent")
    try:
        board.ctrl_transfer(VENDOR_OUT, START, 0, 0, None)
    except usb.core.USBError:
        pass  # the board may leave the bus before the status stage
    log("stage 4: START sent")


def describe_interfaces(accessory) -> str:
    configuration = accessory.get_active_configuration()
    parts = []
    for interface in configuration:
        parts.append(
            f"{interface.bInterfaceNumber}/{interface.bAlternateSetting}:"
            f"class {interface.bInterfaceClass:#04x} sub {interface.bInterfaceSubClass:#04x}"
        )
    return ", ".join(parts)


def answer(accessory, frame: bytes) -> None:
    request = decode_frame(frame)
    reply = Message(
        direction=Direction.FROM_DEVICE,
        command_id=request.command_id,
        transaction_id=request.transaction_id,
        body=STATUS_OK,
    )
    accessory.write(ACCESSORY_ENDPOINT_OUT, encode_frame(reply))
    log(
        f"frame 0x{request.command_id:02x} id {int.from_bytes(request.transaction_id, 'little')}"
        f" ({len(request.body)} body bytes) answered STATUS 0"
    )


def converse(accessory, seconds: float, answer_seconds: float) -> int:
    """Step 6: reads the board's frames and answers each frame in the first
    `answer_seconds`. After that it reads and drops them, as a DEQ that went
    quiet. Returns the count of answered frames."""
    if accessory.is_kernel_driver_active(ACCESSORY_INTERFACE):
        accessory.detach_kernel_driver(ACCESSORY_INTERFACE)
    usb.util.claim_interface(accessory, ACCESSORY_INTERFACE)
    received = bytearray()
    answered = 0
    started = time.monotonic()
    give_up = started + seconds
    while time.monotonic() < give_up:
        try:
            received += bytes(accessory.read(ACCESSORY_ENDPOINT_IN, 512, READ_TIMEOUT_MS))
        except usb.core.USBTimeoutError:
            continue
        while 0xF7 in received:
            end = received.index(0xF7) + 1
            frame = bytes(received[received.find(0xF0):end])
            del received[:end]
            if frame and time.monotonic() - started < answer_seconds:
                answer(accessory, frame)
                answered += 1
            elif frame:
                log(f"frame 0x{decode_frame(frame).command_id:02x} left unanswered")
    return answered


def main() -> int:
    arguments = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    arguments.add_argument("--seconds", type=float, default=30.0, help="how long to hold the conversation")
    arguments.add_argument(
        "--answer-seconds", type=float, default=None,
        help="answer frames only this long, then stay silent (default: the whole run)",
    )
    options = arguments.parse_args()
    answer_seconds = options.seconds if options.answer_seconds is None else options.answer_seconds

    board = find_board({TABLET_PRODUCT_ID}, wait_seconds=10)
    if board is None:
        log("no board as 18d1:4ee7 on the bus; is its USB-OTG port in this laptop?")
        return 1
    log(f"stage 1: found the board as {board.idVendor:04x}:{board.idProduct:04x} ({board.product})")
    run_handshake(board)
    usb.util.dispose_resources(board)

    accessory = find_board(set(ACCESSORY_PRODUCT_IDS), wait_seconds=5)
    if accessory is None:
        log("the board did not come back as an accessory within 5 s")
        return 1
    log(f"stage 4: back as {accessory.idVendor:04x}:{accessory.idProduct:04x}")
    time.sleep(0.5)  # the kernel configures it
    log(f"stage 5: interfaces {describe_interfaces(accessory)}")
    answered = converse(accessory, options.seconds, answer_seconds)
    log(f"stage 6: answered {answered} frames in {options.seconds:.0f} s")
    return 0 if answered > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
