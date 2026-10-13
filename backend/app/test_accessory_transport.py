"""Checks the accessory transport's framing, without a Pi or a socket.

`test_usb_transport.py` works the same way. This file covers the cut of whole
frames out of a byte stream. A real link would most likely catch this code out
there. The gadget relays the DEQ's own framing unchanged, so this file reuses
the same frames and the same pad-byte rule.

The fake is a socket and not a serial port. The two report quiet in different
ways. A socket raises `socket.timeout`, and returns zero bytes only when the
far end closed. The tests below cover both cases, because they mean different
things to a session.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from app.accessory_transport import AccessoryTransport
from app.deq_protocol import Direction, Message, encode_frame
from app.deq_transport import (
    BULK_PACKET_BYTES,
    MAX_FRAME_BYTES,
    TransportError,
    TransportTimeout,
)

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


class FakeGadgetSocket:
    """One Unix socket, backed by bytes in memory.

    It serves the stream that the gadget would relay. You give it that stream.
    It depends on nothing. An exhausted stream raises `socket.timeout`, the way
    a real socket with a timeout set does. A closed far end is a separate
    fixture below, because it means a dead link and not a quiet one.
    """

    def __init__(self, stream: bytes = b"") -> None:
        self.stream = bytearray(stream)
        self.written = bytearray()
        self.timeout: float = 1.0
        self.closed = False

    def settimeout(self, timeout_seconds: float) -> None:
        self.timeout = timeout_seconds

    def recv(self, chunk_bytes: int) -> bytes:
        if len(self.stream) == 0:
            raise socket.timeout("timed out")
        chunk = bytes(self.stream[:chunk_bytes])
        del self.stream[: len(chunk)]
        return chunk

    def sendall(self, data: bytes) -> None:
        self.written += data

    def close(self) -> None:
        self.closed = True


def build_transport(stream: bytes = b"") -> AccessoryTransport:
    """Returns a transport wired to a fake gadget socket, no hardware."""
    return AccessoryTransport(socket_path="unused", connection=FakeGadgetSocket(stream))


def test_a_short_frame_arrives_in_one_read():
    frame = captured_frame("frame-status-request")
    assert len(frame) < BULK_PACKET_BYTES

    transport = build_transport(frame)

    assert transport.receive_frame(1.0) == frame


def test_a_long_frame_is_rebuilt_from_several_reads():
    """The coefficient write is 4209 bytes. A transport that treated one
    read as one frame would truncate it if the gadget split the write."""
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
    """`pack_frame` adds one zero byte when a frame would otherwise be an exact
    multiple of 512. That rule belongs to the DEQ's own USB link, which the
    gadget relays unchanged. The reader has to take that byte with the frame,
    and not leave it to confuse the next read."""
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


def test_a_quiet_gadget_times_out():
    """A timeout means the gadget had nothing to relay, which the session
    reports differently from a broken link."""
    transport = build_transport(b"")
    with pytest.raises(TransportTimeout, match="sent nothing"):
        transport.receive_frame(0.01)


def test_a_closed_socket_is_a_dead_link_and_not_a_timeout():
    """The gadget closes the socket when its session ends: the car slept, or
    the DEQ dropped the link. A session cannot wait that out, so this must not
    look like a slow reply."""
    transport = build_transport()

    class ClosedConnection:
        def settimeout(self, timeout_seconds: float) -> None:
            pass

        def recv(self, chunk_bytes: int) -> bytes:
            return b""

    transport.connection = ClosedConnection()
    with pytest.raises(TransportError, match="closed the link") as caught:
        transport.receive_frame(1.0)
    assert not isinstance(caught.value, TransportTimeout)


def test_a_read_that_fails_for_another_reason_is_not_a_timeout():
    transport = build_transport()

    class BrokenConnection:
        def settimeout(self, timeout_seconds: float) -> None:
            pass

        def recv(self, chunk_bytes: int) -> bytes:
            raise OSError("the socket went away")

    transport.connection = BrokenConnection()
    with pytest.raises(TransportError, match="reading from the gadget failed") as caught:
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

    assert bytes(transport.connection.written) == frame


def test_a_write_that_fails_is_reported():
    transport = build_transport()

    class BrokenConnection:
        def sendall(self, data: bytes) -> None:
            raise OSError("the socket went away")

    transport.connection = BrokenConnection()
    with pytest.raises(TransportError, match="writing 10 bytes to the gadget failed"):
        transport.send_frame(bytes(10))


def test_closing_twice_is_safe():
    transport = build_transport()
    transport.close()
    transport.close()
    assert transport.closed
