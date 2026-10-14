"""A DEQ unit that answers the way the real one does.

This class is a `Transport`, so `DeqSession` talks to it the same way it talks
to a real unit. No mocking library: a test passes one of these through the
session's constructor and reads `exchanges` afterwards.

Every rule below comes from `captures/20260929_session_full.log`. That log
holds real traffic between the Pioneer app and a physical DEQ-S1000A2: 217
matched request and reply pairs.

- the reply's command id equals the request's
- the reply's transaction id equals the request's, byte for byte
- the reply's length field is the request's plus 4
- STATUS, the first four body bytes, is zero
- the reply then echoes the request's own key field, where it has one

The last rule has one exception that matters. **The unit never echoes a payload
array back on a write.** A 2100-byte coefficient write gets a 24-byte
acknowledgement, not a 2104-byte echo. An echoed payload made the real app
refuse a reply with `[Code:601]`, so this fake refuses to echo too.

The fake raises on a command it does not know, and does not answer with zeros.
A silent zero-filled reply hid a real bug for days during the protocol work:
the app kept talking and only failed much later.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.deq_blob import (
    STANDARD_BLOB_BYTES,
    UserConfiguration,
    decode_blob,
    encode_blob,
)
from app.deq_protocol import Direction, Message, decode_frame, encode_frame
from app.deq_session import (
    COMMAND_GET_DRIVING_STATE,
    COMMAND_GET_MODE,
    COMMAND_GET_MUTE_STATE,
    COMMAND_GET_VOLUME,
    COMMAND_PLAY_READY_NOTIFICATION,
    COMMAND_SELF_SAVE_CONFIGURATION_ENABLE,
    COMMAND_SET_MODE,
    COMMAND_SET_MUTE_STATE,
    COMMAND_SET_VOLUME,
    COMMAND_CRASH_REPORT,
    COMMAND_SYSTEM_ERROR_FLAGS,
    COMMAND_DEVICE_IDENTITY,
    COMMAND_FIRMWARE_VERSION,
    COMMAND_READ_USER_CONFIGURATION,
    COMMAND_SYNC,
    COMMAND_WRITE_COEFFICIENTS,
    COMMAND_WRITE_USER_CONFIGURATION,
    CONFIGURATION_PAYLOAD_BYTES,
    STATUS_BYTES,
    STATUS_OK,
)
from app.deq_transport import TransportTimeout

STATUS_OK_BYTES = (0).to_bytes(STATUS_BYTES, "little")

# Above this request payload size the unit acknowledges and does not echo. A
# 20-byte request still gets its field back. A 36-byte coefficient write does
# not.
ECHO_LIMIT_PAYLOAD_BYTES = 28

# What this fake unit reports about itself. Measured from the real
# DEQ-S1000A2 in the car on 2026-10-08, not invented.
FAKE_FIRMWARE_VERSION = 0x0202
FAKE_SERIAL = "ABIV002781EW"

# The 16-byte word the unit returns in its sync reply. The app holds it as a
# constant, `b/a/e$b.a`, and the real unit sent these same bytes.
REPLY_SYNC_WORD = bytes.fromhex("3dd378e1054592964b2ede1fb9283b2b")

# The sync reply the real unit sends is 32 bytes: STATUS, the word above,
# and then the three ASP_STATE fields of `deq_commands.json`.
STATUS_REFUSED_SYNC = -5
# What the real unit answered a volume write with in THROUGH, 2026-10-08.
STATUS_VOLUME_REFUSED = -6

# The volume the car's own unit reported, so the default is a real value.
FAKE_VOLUME_DB = -27

# The source mode a cold start reports. Measured from the real unit on
# 2026-10-08: its `0x0b` reply carried MODE 4, which `deq_enums.json`
# names THROUGH.
FAKE_MODE = 4

# MUTE_STATE wire values, from `deq_enums.json`. The real unit reported
# SOUND_ON and never moved off it, even when told SOUND_OFF.
MUTE_STATE_SOUND_ON = 1
MUTE_STATE_SOUND_OFF = 2

# Which commands still report their own field when they refuse.
#
# A refusal carries STATUS and nothing else, except for the commands here. The
# real unit refused a volume write with STATUS -6 on 2026-10-08. It still
# reported the volume it kept, in `20261008_volume_refusal_reply.hex`. Only
# 0x0d has a measured refusal, so only 0x0d is in this set. Add an id when a
# capture shows it, and not when it seems likely.
COMMANDS_THAT_REPORT_STATE_WHEN_REFUSING = {0x0D}


@dataclass
class Exchange:
    """One request and the reply this fake gave it."""

    request: Message
    reply: Message


@dataclass
class FakeDeq:
    """A DEQ that answers by the rules captured from a real one.

    It replies to the commands a session sends. You hand it to `DeqSession` as
    its transport. It depends on `deq_protocol` to read and write frames, and
    on `deq_blob` for the settings blob it serves.
    """

    configuration: UserConfiguration = field(default_factory=UserConfiguration)
    firmware_version: int = FAKE_FIRMWARE_VERSION
    serial: str = FAKE_SERIAL
    # Set this to stop answering, so a test can see a timeout.
    answers: bool = True

    # The live state the unit reports in its sync reply.
    volume_db: int = FAKE_VOLUME_DB
    muted: bool = False
    driving: bool = False

    # The source mode the unit holds, as an AUDIO_SOURCE wire value. The
    # real unit in the car reported 4, THROUGH, on every cold start.
    mode: int = FAKE_MODE

    # Faults, so a caller can drive the error paths on purpose.
    #
    # `refuses_sync` reproduces what the real unit does when COMMAND_SYNC
    # carries no body: STATUS -5 and then nothing. It is the bug that cost
    # two car sessions, so a fake that cannot reproduce it is not much of a
    # fake.
    refuses_sync: bool = False
    # STATUS to answer with, per command id. Anything not listed answers 0.
    status_by_command: dict[int, int] = field(default_factory=dict)
    # Source modes, as wire values, in which the unit refuses a volume write
    # with STATUS -6. The real unit did that in THROUGH (4) on 2026-10-08,
    # and took one on SP_OTHER_SOURCE. Nobody measured the other modes. The
    # set starts empty, because the captured replies that other tests pin
    # came from sessions that wrote a volume. A test that needs the refusal
    # sets it.
    volume_refused_in_modes: set[int] = field(default_factory=set)
    # Command ids to stop answering after, so a caller can see a timeout
    # mid-sequence rather than only at the start.
    silent_after: set[int] = field(default_factory=set)
    # What 0x17 and 0x15 report. Empty means no fault, which is what the
    # real unit sent.
    error_flags: int = 0
    crash_report: bytes = b""

    exchanges: list[Exchange] = field(default_factory=list)
    sent_frames: list[bytes] = field(default_factory=list)
    _pending_reply: bytes | None = None
    closed: bool = False

    @property
    def command_order(self) -> list[int]:
        """The command ids that this fake received, in order."""
        return [one.request.command_id for one in self.exchanges]

    def send_frame(self, frame: bytes) -> None:
        self.sent_frames.append(frame)
        request = decode_frame(frame)
        if not self.answers:
            # Already quiet: the fake records the request and answers nothing.
            return
        reply = self.build_reply(request)
        self.exchanges.append(Exchange(request=request, reply=reply))
        self._pending_reply = encode_frame(reply)
        if request.command_id in self.silent_after:
            self.answers = False

    def receive_frame(self, timeout_seconds: float) -> bytes:
        """Returns the reply this fake is holding, if it has one.

        A reply already built is still delivered when the unit has gone
        quiet. The real unit sends its refusal and *then* stops answering,
        so swallowing that last frame would hide the refusal itself.
        """
        if self._pending_reply is None:
            raise TransportTimeout(
                f"fake DEQ sent nothing within {timeout_seconds} seconds"
            )
        frame = self._pending_reply
        self._pending_reply = None
        return frame

    def close(self) -> None:
        self.closed = True

    def build_reply(self, request: Message) -> Message:
        """Returns the reply the real unit gives to one request."""
        return Message(
            direction=Direction.FROM_DEVICE,
            command_id=request.command_id,
            transaction_id=request.transaction_id,
            body=self.build_body(request),
        )

    def build_body(self, request: Message) -> bytes:
        """Returns one reply body: STATUS, then whatever the command adds."""
        if request.command_id == COMMAND_SYNC:
            return self.build_sync_body(request)
        if (
            request.command_id == COMMAND_WRITE_USER_CONFIGURATION
            and len(request.body) != CONFIGURATION_PAYLOAD_BYTES
        ):
            # The real unit refused a bare 572-byte blob with STATUS -5 on
            # 2026-10-08. It wants the whole 2028-byte structure.
            return self.status_bytes(STATUS_REFUSED_SYNC)
        status = self.status_by_command.get(request.command_id, STATUS_OK)
        if request.command_id == COMMAND_SET_VOLUME and self.mode in self.volume_refused_in_modes:
            status = STATUS_VOLUME_REFUSED
        if status != STATUS_OK:
            if request.command_id in COMMANDS_THAT_REPORT_STATE_WHEN_REFUSING:
                return self.status_bytes(status) + self.build_tail(request)
            # A failing reply carries STATUS and nothing else, which is what
            # the real unit sent when it refused the opening frame.
            return self.status_bytes(status)
        return STATUS_OK_BYTES + self.build_tail(request)

    def build_sync_body(self, request: Message) -> bytes:
        """Returns the sync reply: STATUS, the word, and the live state.

        The real unit refuses a COMMAND_SYNC that carries no body. It
        answers STATUS -5 with no other field and then stops answering
        anything, so this reproduces both halves.
        """
        if self.refuses_sync or not request.body:
            self.answers = False
            return self.status_bytes(STATUS_REFUSED_SYNC)
        return (
            STATUS_OK_BYTES
            + REPLY_SYNC_WORD
            + self.volume_db.to_bytes(4, "little", signed=True)
            + int(self.muted).to_bytes(4, "little")
            + int(self.driving).to_bytes(4, "little")
        )

    @staticmethod
    def status_bytes(status: int) -> bytes:
        """Returns one STATUS field. Signed: failure is negative."""
        return status.to_bytes(STATUS_BYTES, "little", signed=True)

    def build_tail(self, request: Message) -> bytes:
        """Returns the part of a reply body after STATUS.

        A command with its own reply shape gets a named builder. Everything
        else follows the echo rule measured from the capture.
        """
        if request.command_id == COMMAND_FIRMWARE_VERSION:
            return self.firmware_version.to_bytes(2, "little")
        if request.command_id == COMMAND_DEVICE_IDENTITY:
            return self.build_identity_tail()
        if request.command_id == COMMAND_READ_USER_CONFIGURATION:
            return self.build_configuration_payload()
        if request.command_id == COMMAND_WRITE_USER_CONFIGURATION:
            return self.accept_configuration(request)
        if request.command_id == COMMAND_WRITE_COEFFICIENTS:
            return self.acknowledge_coefficients(request)
        if request.command_id == COMMAND_SYSTEM_ERROR_FLAGS:
            return self.error_flags.to_bytes(4, "little")
        if request.command_id == COMMAND_CRASH_REPORT:
            return self.crash_report
        if request.command_id == COMMAND_SET_MODE:
            return self.accept_mode(request)
        if request.command_id == COMMAND_GET_MODE:
            return self.mode.to_bytes(4, "little", signed=True)
        if request.command_id == COMMAND_SET_VOLUME:
            return self.accept_volume(request)
        if request.command_id == COMMAND_GET_VOLUME:
            return self.volume_db.to_bytes(4, "little", signed=True)
        if request.command_id == COMMAND_SET_MUTE_STATE:
            return self.accept_mute_state(request)
        if request.command_id == COMMAND_GET_MUTE_STATE:
            return self.mute_state_wire_value().to_bytes(4, "little", signed=True)
        if request.command_id == COMMAND_GET_DRIVING_STATE:
            return int(self.driving).to_bytes(4, "little", signed=True)
        if request.command_id == COMMAND_PLAY_READY_NOTIFICATION:
            # `deq_commands.json` gives 0x1a a reply of TRANSACTION_ID and
            # STATUS only, so there is no field to echo.
            return b""
        if request.command_id == COMMAND_SELF_SAVE_CONFIGURATION_ENABLE:
            # Unlike the small commands that the echo rule covers, this reply's
            # own fields (deq_commands.json) are TRANSACTION_ID and STATUS
            # only. The reply does not echo ENABLE_FLAG back.
            return b""
        return self.echo_request_field(request)

    def build_identity_tail(self) -> bytes:
        """DEVICE_ID and the eight zero bytes that follow it.

        Measured from a real DEQ-S1000A2 on 2026-10-08, which answered `0x04`
        with a 24-byte body: four of STATUS, twelve of ASCII serial, eight
        zero. The APK's field table declares 40 payload bytes with SPEAKER_MODE
        at offset 36. This fake sent that at one time. So a field that the unit
        never sends read as a real value in every test. The unit is the
        authority, so this method matches the unit.
        """
        serial_bytes = self.serial.encode("ascii")
        if len(serial_bytes) > 12:
            raise ValueError(f"serial {self.serial!r} does not fit in 12 bytes")
        return serial_bytes.ljust(12, b"\x00") + bytes(8)

    def build_configuration_payload(self) -> bytes:
        """Returns the 2028 bytes `0x09` answers with, blob first.

        A real DEQ-S1000A2 answered with this same count on 2026-10-08. The
        first 572 are the blob this app decodes. The rest were all zero on that
        unit. A bare 572 here hid two real bugs. The reader handed the whole
        body to `decode_blob`, and the writer sent a blob that the unit
        refuses.
        """
        blob = encode_blob(self.configuration)
        return blob.ljust(CONFIGURATION_PAYLOAD_BYTES, b"\x00")

    def accept_configuration(self, request: Message) -> bytes:
        """Stores a written blob, so a later read returns it.

        The unit wants the whole 2028-byte structure and refuses a bare
        572-byte blob with STATUS -5, measured on 2026-10-08. So this
        refuses one too, rather than accepting what the real unit will not.
        """
        self.configuration = decode_blob(request.body[:STANDARD_BLOB_BYTES])
        return b""

    def acknowledge_coefficients(self, request: Message) -> bytes:
        """Answers a coefficient write with its CONFIG_ID and nothing else.

        This rule matters most. The real unit sends 24 payload bytes back for a
        2100-byte write.
        """
        return request.body[:4]

    def accept_mode(self, request: Message) -> bytes:
        """Takes a source mode and reports the unit's whole audio state.

        0x0b answers with four fields, not one: MODE, ASP_STATE_VOLUME,
        ASP_STATE_MUTE_STATE and ASP_STATE_DRIVING_STATE. The generic echo rule
        answered it with MODE alone at one time, and no real unit ever did
        that. `20261008_set_mode_reply.hex` is the real reply.

        The real unit took every mode it received with STATUS 0 and echoed it
        back, so this method does the same. Set `status_by_command` to make it
        refuse instead.
        """
        self.mode = int.from_bytes(request.body, "little", signed=True)
        return b"".join([
            self.mode.to_bytes(4, "little", signed=True),
            self.volume_db.to_bytes(4, "little", signed=True),
            self.mute_state_wire_value().to_bytes(4, "little", signed=True),
            int(self.driving).to_bytes(4, "little", signed=True),
        ])

    def accept_volume(self, request: Message) -> bytes:
        """Takes a volume and reports what the unit now holds.

        A refusal keeps the old volume: the real unit answered STATUS -6
        and still reported -37 dB, which is
        `20261008_volume_refusal_reply.hex`. A caller sets that refusal
        with `status_by_command`, and this method honours it.
        """
        refused = (
            self.status_by_command.get(request.command_id, 0) != 0
            or self.mode in self.volume_refused_in_modes
        )
        if not refused:
            self.volume_db = int.from_bytes(request.body, "little", signed=True)
        return self.volume_db.to_bytes(4, "little", signed=True)

    def accept_mute_state(self, request: Message) -> bytes:
        """Takes a MUTE_STATE and reports what the unit now holds.

        The real unit answered SOUND_OFF with STATUS 0 and then reported
        SOUND_ON anyway: `20261008_mute_state_reply.hex`. So this method takes
        the value, keeps its own state unchanged, and reports SOUND_ON. A unit
        showed only that behaviour.
        """
        return self.mute_state_wire_value().to_bytes(4, "little", signed=True)

    def mute_state_wire_value(self) -> int:
        return MUTE_STATE_SOUND_OFF if self.muted else MUTE_STATE_SOUND_ON

    def echo_request_field(self, request: Message) -> bytes:
        """Echoes a small request's own field back, as the unit does.

        A request big enough to carry a payload array gets an acknowledgement
        instead. See this module's docstring.
        """
        if request.payload_length > ECHO_LIMIT_PAYLOAD_BYTES:
            raise UnknownCommandError(request.command_id, request.payload_length)
        return request.body


class UnknownCommandError(Exception):
    """This fake received a command that it has no measured reply for.

    An answer of zeros would let a test pass against behaviour that no real
    unit ever showed.
    """

    def __init__(self, command_id: int, payload_length: int) -> None:
        super().__init__(
            f"fake DEQ has no reply rule for command 0x{command_id:02x} "
            f"with a {payload_length}-byte payload"
        )
        self.command_id = command_id
        self.payload_length = payload_length
