"""The seam between the DEQ's command sequence and the wire under it.

`DeqSession` drives the conversation, and a transport moves the bytes. The
split lets the same session code run against different links. The tests use a
hand-written fake. libusb serves a unit on a port of the machine that runs this
backend. The Pi serves the unit through its accessory gadget.

A transport carries whole frames, not payloads. `deq_protocol` already knows
where a frame starts and ends, so a transport only has to deliver one when it
has one.
"""

from __future__ import annotations

from typing import Protocol


class TransportError(Exception):
    """The link failed. The message says what a person should check."""


class TransportTimeout(TransportError):
    """No frame arrived before the deadline."""


# One bulk packet on the DEQ's own USB link. The codec's 512-byte pad rule
# depends on this size.
BULK_PACKET_BYTES = 512

# A frame never exceeds this. The biggest one is the 4209-byte coefficient
# write, so this leaves room and still bounds a bad read.
MAX_FRAME_BYTES = 8192

# The same byte that `deq_protocol` writes at the end of a frame. This module
# repeats it and does not import it. The joiner has to depend on nothing, so
# that the framing stays testable with no USB or serial stack. Nibble expansion
# keeps every body byte in `0x00`..`0x0f`, so this marker cannot occur inside a
# body, and a search for it is safe.
FRAME_END_MARKER = 0xF7


class FrameJoiner:
    """Cuts whole frames out of a stream of bytes.

    It takes the bytes a link produces and returns whole frames. You call `add`
    with what you read, and `take` for each frame it now holds. It depends on
    nothing, not even a link.

    Every link to the DEQ carries the same frames. A bulk USB read returns one
    512-byte packet. A serial read returns the bytes that arrived. The Pi's
    accessory device returns one write at a time. So on all three, a frame can
    arrive in pieces, and two frames can arrive together. The rule for finding
    the edge is the same in each case. So it lives here once, and not in each
    transport.

    This class imports nothing optional. So a test can check the framing with
    no USB or serial stack present.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()

    def add(self, data: bytes) -> None:
        """Adds bytes read from the link."""
        self._buffer += data

    def take(self) -> bytes | None:
        """Returns the first whole frame the buffer holds, if it holds one.

        A frame that is an exact multiple of 512 bytes carries one zero byte
        after its end marker. This method takes that byte with the frame.
        """
        end = self._buffer.find(FRAME_END_MARKER)
        if end == -1:
            return None
        length = end + 1
        if length % BULK_PACKET_BYTES == 0 and len(self._buffer) > length:
            length += 1
        frame = bytes(self._buffer[:length])
        del self._buffer[:length]
        return frame

    def raise_if_out_of_step(self) -> None:
        """Fails when the buffer has grown past any real frame.

        A link that never produces an end marker would otherwise buffer
        without limit. The size says the two ends disagree about where a
        frame starts, which no further reading can repair.
        """
        if len(self._buffer) > MAX_FRAME_BYTES:
            raise TransportError(
                f"no frame end in {len(self._buffer)} bytes; the link is out of step"
            )

    def pending_byte_count(self) -> int:
        """Returns how many bytes wait for an end marker."""
        return len(self._buffer)


def receive_frame_by_reading(joiner: FrameJoiner, read_more) -> bytes:
    """Returns the next whole frame, and reads as often as it takes.

    `read_more` returns whatever bytes the link has. It is a parameter and not
    a method, so one loop serves every transport. Each link differs only in the
    call that reads it.
    """
    while True:
        frame = joiner.take()
        if frame is not None:
            return frame
        joiner.raise_if_out_of_step()
        joiner.add(read_more())


class Transport(Protocol):
    """Moves one frame at a time over one link.

    It sends and receives whole frames. You call `send_frame`, then
    `receive_frame`. It depends on whatever link it wraps, and on nothing in
    this app.
    """

    def send_frame(self, frame: bytes) -> None:
        """Puts one frame on the wire."""
        ...

    def receive_frame(self, timeout_seconds: float) -> bytes:
        """Returns the next frame, or raises `TransportTimeout`."""
        ...

    def close(self) -> None:
        """Releases the link. Calling it twice is safe."""
        ...
