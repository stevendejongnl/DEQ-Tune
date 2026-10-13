"""Checks the USB transport's framing, without a USB device.

This file cannot test the parts that need hardware. So it covers the part that
does not: the cut of whole frames out of a stream of 512-byte bulk packets. A
real unit would most likely catch this code out there, because a bulk read
returns one packet and a frame can be far longer.

The frames come from `conformance/flows.json`, so they are the bytes a real
DEQ-S1000A2 put on the wire.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.deq_protocol import Direction, Message, encode_frame
from app.deq_transport import (
    BULK_PACKET_BYTES,
    MAX_FRAME_BYTES,
    TransportError,
    TransportTimeout,
)
from app.usb_transport import UsbTransport, detach_kernel_driver

CORPUS_PATH = Path(__file__).resolve().parents[2] / "conformance" / "flows.json"


def captured_frame(name: str) -> bytes:
    flows = json.loads(CORPUS_PATH.read_text())["flows"]
    return bytes.fromhex(next(flow for flow in flows if flow["name"] == name)["bytesHex"])


def build_frame(body_bytes: int) -> bytes:
    """Returns a real frame whose body is a chosen size."""
    return encode_frame(
        Message(
            direction=Direction.FROM_DEVICE,
            command_id=0x05,
            transaction_id=(1).to_bytes(8, "little"),
            body=bytes(body_bytes),
        )
    )


class FakeEndpoint:
    """One bulk endpoint, backed by bytes in memory.

    It hands out one packet per read, the way a real bulk endpoint does. You
    give it the stream to serve. It depends on nothing.
    """

    def __init__(self, stream: bytes = b"") -> None:
        self.stream = bytearray(stream)
        self.written = bytearray()

    def read(self, packet_bytes: int, timeout_milliseconds: int) -> bytes:
        if self.stream == bytearray():
            raise USBTimeoutError("nothing to read")
        packet = bytes(self.stream[:packet_bytes])
        del self.stream[:packet_bytes]
        return packet

    def write(self, data: bytes) -> int:
        self.written += data
        return len(data)


class USBTimeoutError(Exception):
    """Stands in for `usb.core.USBTimeoutError`.

    The transport tells a timeout apart by the exception's name, so this
    fixture carries the same name rather than the real class. That is what
    lets the framing be tested without `pyusb` installed, which is how CI
    runs.
    """


def build_transport(stream: bytes = b"") -> UsbTransport:
    """Returns a transport wired to fake endpoints, with no USB in sight."""
    return UsbTransport(
        endpoints=(0, FakeEndpoint(stream), FakeEndpoint()),
    )


def test_the_end_marker_cannot_appear_inside_a_frame():
    """What the whole reader rests on.

    A search for `0xf7` is safe only because nibble expansion puts every body
    byte in `0x00`..`0x0f`. So the marker cannot occur in a body, whatever the
    payload holds. This test checks that with a body that carries every byte
    value.
    """
    every_byte_value = bytes(range(256)) * 8
    frame = encode_frame(
        Message(
            direction=Direction.FROM_DEVICE,
            command_id=0x05,
            transaction_id=bytes([0xFF] * 8),
            body=every_byte_value,
        )
    )

    positions = [index for index, value in enumerate(frame) if value == 0xF7]
    assert positions == [len(frame) - 1]


def test_a_short_frame_arrives_in_one_packet():
    frame = captured_frame("frame-status-request")
    assert len(frame) < BULK_PACKET_BYTES

    transport = build_transport(frame)

    assert transport.receive_frame(1.0) == frame


def test_a_long_frame_is_rebuilt_from_several_packets():
    """The coefficient write is 4209 bytes, which is nine bulk packets. A
    transport that treated one read as one frame would truncate it."""
    frame = build_frame(2080)
    assert len(frame) > BULK_PACKET_BYTES * 8

    transport = build_transport(frame)

    assert transport.receive_frame(1.0) == frame


def test_two_frames_in_one_stream_come_back_one_at_a_time():
    first = captured_frame("frame-status-request")
    second = captured_frame("frame-volume-reply")

    transport = build_transport(first + second)

    assert transport.receive_frame(1.0) == first
    assert transport.receive_frame(1.0) == second


def test_a_frame_that_fills_whole_packets_keeps_its_pad_byte():
    """`pack_frame` adds one zero byte when a frame would otherwise be an
    exact multiple of 512. That byte belongs to the frame, so the reader has
    to take it with the frame and not leave it to confuse the next read."""
    padded = next(
        frame
        for body_bytes in range(1, 600)
        for frame in [build_frame(body_bytes)]
        if len(frame) % BULK_PACKET_BYTES == 1
    )
    following = captured_frame("frame-status-request")

    transport = build_transport(padded + following)

    assert transport.receive_frame(1.0) == padded
    assert transport.receive_frame(1.0) == following


def test_a_silent_unit_times_out():
    """A timeout means the unit had nothing to send, which the session
    reports differently from a broken link."""
    transport = build_transport(b"")
    with pytest.raises(TransportTimeout, match="sent nothing"):
        transport.receive_frame(0.01)


def test_a_read_that_fails_for_another_reason_is_not_a_timeout():
    transport = build_transport()

    class BrokenEndpoint:
        def read(self, packet_bytes: int, timeout_milliseconds: int) -> bytes:
            raise OSError("the device went away")

    transport.in_endpoint = BrokenEndpoint()
    with pytest.raises(TransportError, match="reading from the unit failed") as caught:
        transport.receive_frame(1.0)
    assert not isinstance(caught.value, TransportTimeout)


def test_a_stream_with_no_frame_end_is_reported_not_buffered_forever():
    transport = build_transport(bytes(MAX_FRAME_BYTES + BULK_PACKET_BYTES))
    with pytest.raises(TransportError, match="out of step"):
        transport.receive_frame(1.0)


def test_sending_writes_the_whole_frame():
    frame = captured_frame("frame-status-request")
    transport = build_transport()

    transport.send_frame(frame)

    assert bytes(transport.out_endpoint.written) == frame


def test_a_short_write_is_an_error():
    transport = build_transport()

    class ShortEndpoint:
        def write(self, data: bytes) -> int:
            return len(data) - 1

    transport.out_endpoint = ShortEndpoint()
    with pytest.raises(TransportError, match="wrote"):
        transport.send_frame(captured_frame("frame-status-request"))


def test_closing_twice_is_safe():
    transport = build_transport()
    transport.close()
    transport.close()
    assert transport.closed


class FakeDevice:
    """A device that reports whether the kernel holds its interface.

    It answers `is_kernel_driver_active` and records a detach. You set
    `kernel_holds_it`, and it depends on nothing.
    """

    def __init__(self, kernel_holds_it: bool, raises: Exception | None = None) -> None:
        self.kernel_holds_it = kernel_holds_it
        self.raises = raises
        self.detached: list[int] = []

    def is_kernel_driver_active(self, interface_number: int) -> bool:
        if self.raises is not None:
            raise self.raises
        return self.kernel_holds_it

    def detach_kernel_driver(self, interface_number: int) -> None:
        self.detached.append(interface_number)


def test_a_kernel_held_interface_is_detached_before_the_claim():
    """A unit that looks like an audio device gets a kernel driver bound,
    and the claim then fails. The Pioneer app's own libusb exports
    `libusb_detach_kernel_driver` for the same reason."""
    device = FakeDevice(kernel_holds_it=True)

    detach_kernel_driver(device, 0)

    assert device.detached == [0]


def test_an_interface_the_kernel_does_not_hold_is_left_alone():
    device = FakeDevice(kernel_holds_it=False)

    detach_kernel_driver(device, 0)

    assert device.detached == []


def test_a_platform_without_kernel_drivers_is_not_an_error():
    device = FakeDevice(kernel_holds_it=False, raises=NotImplementedError())

    detach_kernel_driver(device, 0)

    assert device.detached == []
