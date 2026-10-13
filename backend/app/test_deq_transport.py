"""Checks the frame joiner, the one piece every link shares.

Each transport differs only in the call that reads bytes. The cut of a frame
out of what that call returns is the same work on all of them. So this file
tests it once, and the transport tests cover their own read.

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
    FrameJoiner,
    TransportError,
    receive_frame_by_reading,
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


def build_padded_frame() -> bytes:
    """Returns a frame that fills whole packets and so carries a pad byte.

    No captured frame lands on a 512-byte boundary, so this searches body
    sizes for one that does. The frame still comes from the real encoder.
    """
    return next(
        frame
        for body_bytes in range(1, 600)
        for frame in [build_frame(body_bytes)]
        if len(frame) % BULK_PACKET_BYTES == 1
    )


class FakeLink:
    """Hands out a byte stream in pieces of a fixed size.

    It answers one read at a time, and `receive_frame_by_reading` calls it. It
    depends on nothing. A piece size of one byte is the hardest case for the
    joiner, so a test can ask for that.
    """

    def __init__(self, stream: bytes, piece_size: int = BULK_PACKET_BYTES) -> None:
        self.stream = stream
        self.piece_size = piece_size
        self.position = 0
        self.read_count = 0

    def read(self) -> bytes:
        self.read_count += 1
        piece = self.stream[self.position : self.position + self.piece_size]
        self.position += len(piece)
        return piece


def test_an_empty_joiner_holds_no_frame():
    assert FrameJoiner().take() is None


def test_a_partial_frame_is_held_until_its_end_arrives():
    frame = captured_frame("frame-status-request")
    joiner = FrameJoiner()

    joiner.add(frame[:-1])

    assert joiner.take() is None

    joiner.add(frame[-1:])

    assert joiner.take() == frame


def test_two_frames_added_together_come_back_one_at_a_time():
    first = captured_frame("frame-status-request")
    second = captured_frame("frame-status-reply")
    joiner = FrameJoiner()

    joiner.add(first + second)

    assert joiner.take() == first
    assert joiner.take() == second
    assert joiner.take() is None


def test_a_frame_that_fills_whole_packets_keeps_its_pad_byte():
    """The rule that makes this class worth having in one place.

    A frame whose length is an exact multiple of 512 carries one zero byte
    after its end marker. Taking the frame without that byte would leave it
    at the front of the buffer, where it reads as the start of the next
    frame.
    """
    padded = build_padded_frame()
    following = captured_frame("frame-status-request")
    joiner = FrameJoiner()

    joiner.add(padded + following)

    assert joiner.take() == padded
    assert joiner.take() == following
    assert joiner.pending_byte_count() == 0


def test_a_buffer_past_any_real_frame_is_reported():
    joiner = FrameJoiner()

    joiner.add(b"\x00" * (MAX_FRAME_BYTES + 1))

    with pytest.raises(TransportError, match="out of step"):
        joiner.raise_if_out_of_step()


def test_a_buffer_within_bounds_is_not_reported():
    joiner = FrameJoiner()

    joiner.add(b"\x00" * MAX_FRAME_BYTES)

    joiner.raise_if_out_of_step()


def test_reading_returns_a_frame_that_arrived_in_one_piece():
    frame = captured_frame("frame-status-request")
    link = FakeLink(frame)

    assert receive_frame_by_reading(FrameJoiner(), link.read) == frame
    assert link.read_count == 1


def test_reading_rebuilds_a_frame_that_arrived_one_byte_at_a_time():
    """The worst case a link can produce, and the one a fixed read misses."""
    frame = captured_frame("frame-status-request")
    link = FakeLink(frame, piece_size=1)

    assert receive_frame_by_reading(FrameJoiner(), link.read) == frame
    assert link.read_count == len(frame)


def test_reading_leaves_the_second_frame_for_the_next_call():
    first = captured_frame("frame-status-request")
    second = captured_frame("frame-status-reply")
    link = FakeLink(first + second)
    joiner = FrameJoiner()

    assert receive_frame_by_reading(joiner, link.read) == first
    assert receive_frame_by_reading(joiner, link.read) == second


def test_reading_a_stream_with_no_frame_end_is_reported_not_buffered_forever():
    link = FakeLink(b"\x00" * (MAX_FRAME_BYTES * 2))

    with pytest.raises(TransportError, match="out of step"):
        receive_frame_by_reading(FrameJoiner(), link.read)
