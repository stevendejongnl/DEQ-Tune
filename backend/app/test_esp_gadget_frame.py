"""Checks that the ESP gadget's C frame codec matches this backend's.

`esp-gadget/main/deq_frame.c` repeats `encode_frame` and `decode_frame` in
C, because the ESP32-S3 runs no Python. Two codecs for one wire format
drift apart, so this test compiles the C file for the laptop with the
system's C compiler and runs both on the same frames. The replies come
from a real unit, captured on 2026-10-08.
"""

from __future__ import annotations

import ctypes
import shutil
import subprocess
from pathlib import Path

import pytest

from app.deq_protocol import Direction, Message, decode_frame, encode_frame

CODEC_SOURCE = Path(__file__).resolve().parents[2] / "esp-gadget" / "main" / "deq_frame.c"
CAPTURES = Path(__file__).resolve().parent / "testing" / "captures"
COMPILER = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")

# A backend tree copied to the Pi has no `esp-gadget/` beside it, and a
# machine with no C compiler cannot build the codec. CI has both.
pytestmark = pytest.mark.skipif(
    not CODEC_SOURCE.exists() or COMPILER is None,
    reason="no esp-gadget/ beside this backend tree, or no C compiler",
)

JOINER_BUFFER_BYTES = 8192


class ParsedFrame(ctypes.Structure):
    _fields_ = [
        ("direction", ctypes.c_uint16),
        ("command_id", ctypes.c_uint16),
        ("transaction_id", ctypes.c_uint64),
        ("has_status", ctypes.c_bool),
        ("status", ctypes.c_int32),
        ("body_length", ctypes.c_size_t),
    ]


class FrameJoiner(ctypes.Structure):
    _fields_ = [("buffer", ctypes.c_uint8 * JOINER_BUFFER_BYTES), ("length", ctypes.c_size_t)]


FOUND_FRAME = ctypes.CFUNCTYPE(None, ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t, ctypes.c_void_p)


@pytest.fixture(scope="module")
def codec(tmp_path_factory) -> ctypes.CDLL:
    library = tmp_path_factory.mktemp("codec") / "libdeqframe.so"
    subprocess.run(
        [COMPILER, "-shared", "-fPIC", "-std=c11", "-Wall", "-Werror", "-o", str(library), str(CODEC_SOURCE)],
        check=True,
    )
    loaded = ctypes.CDLL(str(library))
    loaded.deq_frame_build.restype = ctypes.c_size_t
    loaded.deq_frame_build.argtypes = [
        ctypes.c_uint16,
        ctypes.c_uint64,
        ctypes.c_char_p,
        ctypes.c_size_t,
        ctypes.c_char_p,
        ctypes.c_size_t,
    ]
    loaded.deq_frame_parse.restype = ctypes.c_bool
    loaded.deq_frame_parse.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(ParsedFrame)]
    loaded.deq_frame_joiner_feed.argtypes = [
        ctypes.POINTER(FrameJoiner),
        ctypes.c_char_p,
        ctypes.c_size_t,
        FOUND_FRAME,
        ctypes.c_void_p,
    ]
    return loaded


def build_with_c(codec: ctypes.CDLL, command_id: int, transaction_id: int, body: bytes) -> bytes:
    frame = ctypes.create_string_buffer(2 * len(body) + 64)
    length = codec.deq_frame_build(command_id, transaction_id, body, len(body), frame, len(frame))
    return frame.raw[:length]


def build_with_backend(command_id: int, transaction_id: int, body: bytes) -> bytes:
    return encode_frame(
        Message(
            direction=Direction.TO_DEVICE,
            command_id=command_id,
            transaction_id=transaction_id.to_bytes(8, "little"),
            body=body,
        )
    )


@pytest.mark.parametrize(
    ("command_id", "transaction_id", "body"),
    [
        # The cold start's opening COMMAND_SYNC, with the app's 24 bytes.
        (0x00, 1, bytes.fromhex("a5c543847b356c8c408b701679ce1f110000000000000000")),
        (0x21, 2, bytes.fromhex("10270000")),
        (0x17, 3, b""),
        (0x02, 0xFF, b""),
        (0x0D, 0x1234, bytes.fromhex("f2ffffff")),
        # The coefficient write is 4209 bytes on the wire.
        (0x05, 0x42, bytes(range(256)) * 8 + bytes(32)),
    ],
)
def test_the_c_encoder_writes_the_backends_bytes(codec, command_id, transaction_id, body):
    assert build_with_c(codec, command_id, transaction_id, body) == build_with_backend(
        command_id, transaction_id, body
    )


def test_the_c_encoder_refuses_a_frame_that_does_not_fit(codec):
    frame = ctypes.create_string_buffer(10)

    assert codec.deq_frame_build(0x00, 1, b"", 0, frame, len(frame)) == 0


@pytest.mark.parametrize("capture", sorted(CAPTURES.glob("*_reply.hex")), ids=lambda path: path.stem)
def test_the_c_parser_reads_a_real_reply_as_the_backend_does(codec, capture):
    frame = bytes.fromhex(capture.read_text().strip())
    expected = decode_frame(frame)
    parsed = ParsedFrame()

    assert codec.deq_frame_parse(frame, len(frame), ctypes.byref(parsed))

    assert parsed.direction == int(expected.direction)
    assert parsed.command_id == expected.command_id
    assert parsed.transaction_id == int.from_bytes(expected.transaction_id, "little")
    assert parsed.body_length == len(expected.body)
    assert parsed.has_status
    assert parsed.status == int.from_bytes(expected.body[:4], "little", signed=True)


def test_the_joiner_finds_frames_split_across_chunks(codec):
    first = build_with_backend(0x00, 1, bytes(24))
    second = build_with_backend(0x02, 2, b"")
    stream = first + bytes([0x00]) + second
    found: list[bytes] = []

    @FOUND_FRAME
    def collect(frame, length, _context):
        found.append(ctypes.string_at(frame, length))

    joiner = FrameJoiner()
    for start in range(0, len(stream), 7):
        chunk = stream[start:start + 7]
        codec.deq_frame_joiner_feed(ctypes.byref(joiner), chunk, len(chunk), collect, None)

    assert found == [first, second]
