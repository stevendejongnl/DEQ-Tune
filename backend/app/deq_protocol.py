"""Reads and writes the Pioneer DEQ's USB message format.

The DEQ speaks a SysEx-style framing over Android Open Accessory. The DEQ is
the accessory and the phone, or this app, is the host.

The rules here come from the Sound & Tune app's own codec, `b/g/d.pack()` and
`b/g/c.unpack()` in the decompiled APK. Captured traffic between the real app
and a real unit then checked them. An earlier version of this module guessed
the layout from raw byte offsets. Those offsets landed inside the nibble-packed
payload, and gave the right values for two cases by chance. This version is the
decoded rule.

A frame on the wire:

    0xf0
    header A, 3 bytes: 00 40 06
    header B, 4 bytes: 00 00 00 01
    the payload, nibble-expanded: each payload byte becomes two bytes,
        high nibble first, each in the range 0x00..0x0f
    0xf7
    one 0x00, but only when the frame would otherwise be an exact
        multiple of 512 bytes

Nibble expansion keeps every payload byte below 0x80, so the payload can never
look like a MIDI status byte. The frame holds no payload length. A reader
derives it from the frame size.

A payload, once unpacked, is little-endian throughout:

    0..1    direction: 1 for host to DEQ, 2 for DEQ to host
    2..3    command id
    4..7    length, which is the payload length minus 8
    8..15   transaction id, mirrored unchanged into the reply
    16..    the command's own fields

`deq_commands.json` lists every command's fields for both directions. A
generator builds it from the field enums in the APK. So it covers commands that
this app never saw on the wire.

Two traps in that table:

- A declared field width is a floor, and not the truth. Command 0x05 says
  its CONFIGURATION is 16 bytes. A real equalizer write carries 2080.
  Read a configuration as "the rest of the payload".
- The pad rule above can never fire with the 7-byte header this unit
  uses. A frame is then always an odd number of bytes. The codec keeps the
  rule, because the header comes from a config object that another unit
  could set differently.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

FRAME_START_MARKER = 0xF0
FRAME_END_MARKER = 0xF7
FRAME_HEADER_A = bytes([0x00, 0x40, 0x06])
FRAME_HEADER_B = bytes([0x00, 0x00, 0x00, 0x01])

# A frame whose length is an exact multiple of this gets one extra 0x00.
FRAME_PAD_MULTIPLE = 512

DIRECTION_OFFSET = 0
COMMAND_ID_OFFSET = 2
LENGTH_OFFSET = 4
TRANSACTION_ID_OFFSET = 8
BODY_OFFSET = 16

# A notification carries no transaction id, so its body starts where the
# transaction id would be. Nothing asked for the frame, so there is no id
# to mirror back. Measured from a real unit on 2026-10-08: a 12-byte
# payload, of which the last four are the value.
NOTIFICATION_BODY_OFFSET = 8

# The length field counts the payload from the transaction id onwards.
LENGTH_FIELD_BIAS = 8

TRANSACTION_ID_BYTES = 8


class Direction(IntEnum):
    TO_DEVICE = 1
    FROM_DEVICE = 2
    # A frame the unit sends with nothing having asked for it. Measured on
    # 2026-10-08: turning the car's own volume knob made a real
    # DEQ-S1000A2 push one of these per step. See NOTIFICATION_BODY_OFFSET
    # for how its header differs.
    NOTIFICATION = 3


class InvalidFrameError(ValueError):
    """Raised when a byte string is not a frame this codec can read."""


def pack_frame(payload: bytes) -> bytes:
    """Returns the frame that carries one payload."""
    frame = bytearray()
    frame.append(FRAME_START_MARKER)
    frame += FRAME_HEADER_A
    frame += FRAME_HEADER_B
    for payload_byte in payload:
        frame.append((payload_byte >> 4) & 0x0F)
        frame.append(payload_byte & 0x0F)
    frame.append(FRAME_END_MARKER)
    if len(frame) % FRAME_PAD_MULTIPLE == 0:
        frame.append(0x00)
    return bytes(frame)


def unpack_frame(frame: bytes) -> bytes:
    """Returns the payload a frame carries.

    Header A is 3 bytes when the byte after the start marker is zero, and 1
    byte otherwise. Every frame seen so far takes the 3-byte form, but the
    app's own reader handles both, so this one does too.
    """
    if len(frame) < 10 or frame[0] != FRAME_START_MARKER:
        raise InvalidFrameError("frame does not start with 0xf0")
    header_a_length = 3 if frame[1] == 0x00 else 1
    body_start = 1 + header_a_length + len(FRAME_HEADER_B)
    nibble_count = len(frame) - body_start - 1
    payload = bytearray()
    for position in range(nibble_count // 2):
        index = body_start + position * 2
        payload.append(((frame[index] & 0x0F) << 4) | (frame[index + 1] & 0x0F))
    return bytes(payload)


@dataclass(frozen=True)
class Message:
    """One decoded payload."""

    direction: Direction
    command_id: int
    transaction_id: bytes
    body: bytes = b""
    # The length that the payload claimed. It should equal the real one. This
    # function keeps a frame that disagrees as it is, so a caller can see the
    # disagreement.
    declared_length: int | None = field(default=None, compare=False)

    @property
    def payload_length(self) -> int:
        return BODY_OFFSET + len(self.body)

    @property
    def length_field_is_consistent(self) -> bool:
        if self.declared_length is None:
            return True
        return self.declared_length == self.payload_length - LENGTH_FIELD_BIAS


def encode_message(message: Message) -> bytes:
    """Returns the payload for one message, with its length field filled in."""
    if len(message.transaction_id) != TRANSACTION_ID_BYTES:
        raise ValueError(
            f"transaction id must be {TRANSACTION_ID_BYTES} bytes, "
            f"got {len(message.transaction_id)}"
        )
    payload = bytearray(BODY_OFFSET)
    payload[DIRECTION_OFFSET:DIRECTION_OFFSET + 2] = int(
        message.direction
    ).to_bytes(2, "little")
    payload[COMMAND_ID_OFFSET:COMMAND_ID_OFFSET + 2] = message.command_id.to_bytes(
        2, "little"
    )
    payload[LENGTH_OFFSET:LENGTH_OFFSET + 4] = (
        BODY_OFFSET + len(message.body) - LENGTH_FIELD_BIAS
    ).to_bytes(4, "little")
    payload[TRANSACTION_ID_OFFSET:BODY_OFFSET] = message.transaction_id
    return bytes(payload) + message.body


def decode_message(payload: bytes) -> Message:
    """Returns the message one payload carries.

    A notification is shorter than a reply and has no transaction id. So the
    body offset depends on the direction. An earlier version read every frame
    at the reply's offset, and a real unit then looked silent. On 2026-10-08 it
    pushed a volume notification per knob step. The reader rejected each one as
    "shorter than its header".
    """
    direction = read_direction(payload)
    body_offset = (
        NOTIFICATION_BODY_OFFSET
        if direction == Direction.NOTIFICATION
        else BODY_OFFSET
    )
    if len(payload) < body_offset:
        raise InvalidFrameError(
            f"payload of {len(payload)} bytes is shorter than its header"
        )
    return Message(
        direction=direction,
        command_id=int.from_bytes(payload[COMMAND_ID_OFFSET:COMMAND_ID_OFFSET + 2], "little"),
        transaction_id=payload[TRANSACTION_ID_OFFSET:body_offset],
        body=payload[body_offset:],
        declared_length=int.from_bytes(payload[LENGTH_OFFSET:LENGTH_OFFSET + 4], "little"),
    )


def read_direction(payload: bytes) -> Direction:
    """Returns which way one payload travels, or says it cannot tell."""
    if len(payload) < LENGTH_OFFSET:
        raise InvalidFrameError(
            f"payload of {len(payload)} bytes is shorter than its header"
        )
    direction_value = int.from_bytes(
        payload[DIRECTION_OFFSET:DIRECTION_OFFSET + 2], "little"
    )
    try:
        return Direction(direction_value)
    except ValueError as caught_error:
        raise InvalidFrameError(f"unknown direction {direction_value}") from caught_error


def encode_frame(message: Message) -> bytes:
    """Returns the wire frame for one message."""
    return pack_frame(encode_message(message))


def decode_frame(frame: bytes) -> Message:
    """Returns the message one wire frame carries."""
    return decode_message(unpack_frame(frame))


@dataclass(frozen=True)
class CommandField:
    """One named field of a command, as the APK's own enum describes it."""

    offset: int
    name: str
    width: int

    @property
    def is_variable_length(self) -> bool:
        """A width of zero marks a field that fills the rest of the payload."""
        return self.width == 0


@dataclass(frozen=True)
class CommandSide:
    """One direction of one command."""

    apk_class: str
    fields: tuple[CommandField, ...]
    payload_bytes: int | None

    def field_named(self, name: str) -> CommandField | None:
        for command_field in self.fields:
            if command_field.name == name:
                return command_field
        return None


@dataclass(frozen=True)
class CommandSpec:
    """Both directions of one command."""

    command_id: int
    request: CommandSide | None
    reply: CommandSide | None


def _load_command_specs() -> dict[int, CommandSpec]:
    path = Path(__file__).parent / "deq_commands.json"
    raw = json.loads(path.read_text())
    specs: dict[int, CommandSpec] = {}
    for command_key, sides in raw.items():
        command_id = int(command_key, 16)
        specs[command_id] = CommandSpec(
            command_id=command_id,
            request=_load_side(sides.get("request")),
            reply=_load_side(sides.get("reply")),
        )
    return specs


def _load_side(side: dict | None) -> CommandSide | None:
    if side is None:
        return None
    return CommandSide(
        apk_class=side["apk_class"],
        fields=tuple(
            CommandField(offset=one["offset"], name=one["name"], width=one["width"])
            for one in side["fields"]
        ),
        payload_bytes=side["payload_bytes"],
    )


COMMAND_SPECS: dict[int, CommandSpec] = _load_command_specs()


def read_field(payload: bytes, command_field: CommandField) -> int:
    """Returns one fixed-width field of a payload as an unsigned integer."""
    if command_field.is_variable_length:
        raise ValueError(f"{command_field.name} has no fixed width")
    end = command_field.offset + command_field.width
    if len(payload) < end:
        raise InvalidFrameError(
            f"payload of {len(payload)} bytes does not reach {command_field.name}"
        )
    return int.from_bytes(payload[command_field.offset:end], "little")


# The bodies the app's cold start carries, read from the APK and not guessed.
#
# The app opens with 0x00 and then sends 0x21 before any read. A DEQ that
# answers only the 0x00 and then nothing is refusing the open: see SYNC_BODY
# below for the body that 0x00 must carry.
#
# `b/e/ai.k()` returns 0x2710, which is 10000, as the only TIMEOUT_INTERVAL the
# app ever sends. The APK holds this value as a constant, so the backend has
# nothing to choose.
TIMEOUT_INTERVAL_MILLISECONDS = 10000

# `b/e.d()` calls `c(I)` with v5, which `const/4 v5, 0x0` sets at the top of
# the method, so the app asks for configuration 0.
INITIAL_CONFIG_ID = 0

TIMEOUT_INTERVAL_BYTES = 4
CONFIG_ID_BYTES = 4


def build_set_timeout_interval_body(
    timeout_interval_milliseconds: int = TIMEOUT_INTERVAL_MILLISECONDS,
) -> bytes:
    """Returns the body of command 0x21, the frame the app sends second.

    `b/e/ai.h()` writes the transaction id and then this one field, so the
    body is the field alone.
    """
    return timeout_interval_milliseconds.to_bytes(TIMEOUT_INTERVAL_BYTES, "little")


def build_get_opal_configuration_body(config_id: int = INITIAL_CONFIG_ID) -> bytes:
    """Returns the body of command 0x06, GET_OPAL_CONFIGURATION.

    `b/e/i.h()` writes the transaction id and then the CONFIG_ID, so the body
    is the config id alone.
    """
    return config_id.to_bytes(CONFIG_ID_BYTES, "little")


# The body of command 0x00, COMMAND_SYNC, which opens a session.
#
# The DEQ refuses a 0x00 that carries no body: it answers STATUS -5 and then
# ignores every frame that follows. The app sends these 24 bytes.
#
# `b/e/b.h()` builds it, and every part is a constant:
#
#   bytes 0..15   `b/a/e$a.b`, a 16-byte literal in the APK
#   bytes 16..19  a boolean, false, which `b/g/a.b(Z)` writes as four zeros
#   bytes 20..23  a zero int
#
# An earlier reading of the APK took 0x00 for a special-cased command. It is
# not one. `b/e/q` is a different request that the cold start never sends. The
# app's 0x00 is `b/e/b` and goes through the normal packer.
#
# Two checks agree. The literal above decodes to these bytes. Five emulator
# cold starts between 2026-10-01 and 2026-10-08 put the same bytes on the wire.
#
# A real unit accepted these bytes on 2026-10-08 and then answered every
# command of the cold start with STATUS 0.
SYNC_BODY = bytes.fromhex("a5c543847b356c8c408b701679ce1f110000000000000000")


def build_sync_body() -> bytes:
    """Returns the body of command 0x00, the frame that opens a session."""
    return SYNC_BODY
