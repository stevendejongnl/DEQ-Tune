"""Drives the conversation with the DEQ.

`deq_protocol` says what one message looks like. This module says which
messages to send, in what order, and what a reply has to satisfy before the
app believes it.

The order comes from the real app. `USB_CAPTURE_NOTES.md` records the
sequence the Sound & Tune app sends on connect, read from a session that
reached a working connected state, and the same order appears in traffic
captured from a physical unit. The app is the authority on it, so
`STARTUP_STEPS` copies that order rather than inventing one.

Roles are the other way around from the capture. There the app is the host
and the DEQ answers. This app takes the host's place, so it sends those
commands and reads the DEQ's replies.

Three rules every reply must satisfy, all three confirmed against captured
traffic between the app and a real DEQ-S1000A2:

- the reply's command id equals the request's
- the reply's transaction id equals the request's, byte for byte
- STATUS, the first four body bytes, is zero

A reply that breaks one of these is not a reply to our request. The app's
own error codes come from the same checks: it raises `[Code:601]` when a
reply's content does not fit the request it answers.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.deq_blob import (
    BANK_B,
    STANDARD_BLOB_BYTES,
    UserConfiguration,
    decode_blob,
    encode_blob,
)
from app.deq_enums import AUDIO_SOURCE, EQ_STYLE, LIVE_SIMULATION, MUTE_STATE
from app.deq_dsp import (
    CROSSOVER_SLOT_COUNT,
    TIME_ALIGNMENT_SLOT_COUNT,
    FilterSlope,
    build_crossover_payload,
    build_equalizer_payload,
    build_time_alignment_payload,
    crossover_slot_settings,
)
from app.deq_protocol import (
    TRANSACTION_ID_BYTES,
    Direction,
    Message,
    build_get_opal_configuration_body,
    build_set_timeout_interval_body,
    build_sync_body,
    decode_frame,
    encode_frame,
)
from app.deq_transport import Transport, TransportTimeout
from app.eq_data import TuningData

# Command ids. The APK names every one of them in its own debug screen,
# `fragment/playground/i$d`, which is an enum of (name, ordinal, wire
# value). The names below are that enum's, not guesses, and each one
# agrees with the request and reply fields `deq_commands.json` carries for
# the same id. Read the enum before inventing a name: four of the names
# here used to be wrong, and one of them sent a read at the wrong command
# for three weeks.
#
#   0x00 CONNECT          0x01 SEND             0x02 PING
#   0x03 GET_VERSION      0x04 GET_HW_INFORMATION
#   0x05 SET_OPAL_CONFIGURATION   0x06 GET_OPAL_CONFIGURATION
#   0x07 SAVE_OPAL_CONFIGURATION  0x08 WRITE_USER_CONFIGURATION
#   0x09 READ_USER_CONFIGURATION  0x0a GET_USER_LOG
#   0x0b SET_MODE         0x0c GET_MODE
#   0x0d SET_VOLUME       0x0e GET_VOLUME
#   0x0f SET_MUTE_STATE   0x10 GET_MUTE_STATE
#   0x11 GET_DRIVING_STATE        0x12 RESET
#   0x13 SET_SPEAKER_MUTE_STATE   0x14 GET_SPEAKER_MUTE_STATE
#   0x15 GET_CRASH_REPORT 0x16 ERASE_CRASH_REPORT
#   0x17 GET_SYSTEM_ERROR_FLAGS   0x18 TOGGLE_USB_MODE
#   0x19 SELF_SAVE_OPAL_CONFIGURATION_ENABLE
#   0x1a PLAY_READY_NOTIFICATION
#   0x1b SET_SYSTEM_MUTE_STATE    0x1c GET_SYSTEM_MUTE_STATE
#   0x1d ISSUE_REQUEST_APP_LAUNCH 0x1e RESET_EEPROM
#   0x1f SET_USB_CONDITIONER_CONFIGURATION_TABLE
#   0x20 GET_USB_CONDITIONER_CONFIGURATION_TABLE
#   0x21 SET_TIMEOUT_INTERVAL
COMMAND_CONNECT = 0x00
COMMAND_KEEPALIVE = 0x02
COMMAND_FIRMWARE_VERSION = 0x03
COMMAND_DEVICE_IDENTITY = 0x04
COMMAND_WRITE_COEFFICIENTS = 0x05
COMMAND_READ_CONFIGURATION_TABLE = 0x06
COMMAND_WRITE_USER_CONFIGURATION = 0x08
COMMAND_READ_USER_CONFIGURATION = 0x09
COMMAND_GET_USER_LOG = 0x0A
COMMAND_SET_MODE = 0x0B
COMMAND_GET_MODE = 0x0C
COMMAND_SET_VOLUME = 0x0D
COMMAND_GET_VOLUME = 0x0E
COMMAND_SET_MUTE_STATE = 0x0F
COMMAND_GET_MUTE_STATE = 0x10
COMMAND_GET_DRIVING_STATE = 0x11
COMMAND_CRASH_REPORT = 0x15
COMMAND_SYSTEM_ERROR_FLAGS = 0x17
COMMAND_SELF_SAVE_CONFIGURATION_ENABLE = 0x19
COMMAND_PLAY_READY_NOTIFICATION = 0x1A
COMMAND_SET_USB_CONDITIONER_TABLE = 0x1F
COMMAND_GET_USB_CONDITIONER_TABLE = 0x20
COMMAND_SET_TIMEOUT_INTERVAL = 0x21

# `COMMAND_SYNC` was this program's name for 0x00 before the APK's own
# enum was read. It is kept so nothing that imports it breaks.
COMMAND_SYNC = COMMAND_CONNECT

# Which CONFIG_ID carries which block of command 0x05. Read from the APK:
# `b/e/ab`'s dispatch maps each id to the field enum that declares its
# CONFIGURATION size, and the sizes settle the mapping.
#
#   id 10 -> af$a$g, 0x20 = 32 bytes, two 16-byte time-alignment blocks
#   id 11 -> af$a$e, 0xb8 = 184 bytes, the standard crossover
#   id 12 -> af$a$f, 0x1a8 = 424 bytes, the network crossover
#   id 13 -> af$a$h, 0x82c = 2080 bytes, the equalizer
#
# The 2080 and the two crossover sizes match `conformance/flows.json` byte
# for byte, so the mapping is checked, not assumed.
CONFIG_ID_TIME_ALIGNMENT = 10
CONFIG_ID_CROSSOVER_STANDARD = 11
CONFIG_ID_CROSSOVER_NETWORK = 12
CONFIG_ID_EQUALIZER = 13

# The slots a profile speaks for: the front and rear high-pass filters.
# Every other slot belongs to the unit's own settings blob.
PROFILE_CROSSOVER_SLOT_COUNT = 2

# A crossover layout and the CONFIG_ID that carries it.
CROSSOVER_CONFIG_IDS = {
    "standard": CONFIG_ID_CROSSOVER_STANDARD,
    "standard_rear": CONFIG_ID_CROSSOVER_STANDARD,
    "network": CONFIG_ID_CROSSOVER_NETWORK,
}

# The order the unit's time-alignment slots sit in, from `w$a` in the APK.
# A profile that drives no subwoofer still fills the fifth slot.
TIME_ALIGNMENT_CHANNELS = ("FL", "FR", "RL", "RR")

STATUS_OFFSET = 0
STATUS_BYTES = 4
STATUS_OK = 0

# How many bytes `0x08`'s USER_CONFIGURATION field carries, from
# `deq_commands.json`. It is the whole structure, of which this app decodes
# the first 572; `0x09` returns exactly this many after its STATUS. A real
# unit refused a bare 572-byte write with STATUS -5.
CONFIGURATION_PAYLOAD_BYTES = 2028

# How long to wait for one reply. The app's own keepalive runs about every
# nine seconds, so a reply that takes longer than this is a dead link.
DEFAULT_TIMEOUT_SECONDS = 5.0

# Which input the unit plays once a link is up. THROUGH passes the car's
# own audio through, so connecting this app never costs a person their
# radio.
#
# This is the app's own choice, not a guess. The real Sound & Tune app was
# run against a fake accessory in the emulator on 2026-10-08, and its cold
# start sends `0x0b` with body `04000000` -- SourceMode THROUGH, wire
# value 4. See `DeqSession.set_audio_source`.
DEFAULT_AUDIO_SOURCE = "THROUGH"

# The order the app sends on connect. Each entry is a command id and the
# body to send with it; a body of `b""` means the command carries nothing
# but its transaction id.
STARTUP_STEPS: tuple[tuple[int, bytes], ...] = (
    # COMMAND_SYNC must carry its body. A real DEQ refused an empty one in
    # the car on 2026-10-08 with STATUS -5 and then ignored every frame
    # after it. See SYNC_BODY in deq_protocol.
    (COMMAND_SYNC, build_sync_body()),
    # The app sends this second, before any read, and always with 10000.
    (COMMAND_SET_TIMEOUT_INTERVAL, build_set_timeout_interval_body()),
    (COMMAND_SYSTEM_ERROR_FLAGS, b""),
    (COMMAND_CRASH_REPORT, b""),
    (COMMAND_FIRMWARE_VERSION, b""),
    (COMMAND_DEVICE_IDENTITY, b""),
    (COMMAND_GET_USER_LOG, b""),
    (COMMAND_GET_USB_CONDITIONER_TABLE, b""),
    (COMMAND_READ_USER_CONFIGURATION, b""),
    (COMMAND_READ_CONFIGURATION_TABLE, build_get_opal_configuration_body()),
    # This sequence is the app's own, with every writing command removed.
    # The app also sends 0x16, 0x1f, 0x05 (twice), 0x19, 0x0d, 0x0b and
    # 0x1a. All of those change the unit: 0x16 erases its crash log, 0x1f
    # is a SET, and the rest write tuning, coefficients, volume or mode.
    # A connect should read and change nothing, so none is sent here.
    # Three of them were sent by an earlier version of this list -- 0x16,
    # 0x1f and COMMAND_SELF_SAVE_CONFIGURATION_ENABLE -- and should not have been.
)


class SessionError(Exception):
    """The conversation with the unit failed."""


class ReplyMismatchError(SessionError):
    """A reply did not answer the request that was sent."""


class SessionTimeoutError(SessionError):
    """The unit did not answer in time."""


class DeviceStatusError(SessionError):
    """The unit answered, and said no.

    `status` is the value it reported. Non-zero means it refused the
    request; the app surfaces the same condition as a communication error.
    """

    def __init__(self, command_id: int, status: int) -> None:
        super().__init__(f"command 0x{command_id:02x} returned status {status}")
        self.command_id = command_id
        self.status = status


@dataclass(frozen=True)
class DeviceIdentity:
    """What the unit says it is, for the header to show."""

    firmware_version: int
    serial: str
    # No speaker mode here, though `deq_commands.json` declares one. The
    # APK says `0x04` answers with 40 payload bytes and SPEAKER_MODE at
    # offset 36; a real DEQ-S1000A2 answered with 24 on 2026-10-08 -- four
    # of STATUS, twelve of ASCII serial, eight zero. So the field is past
    # the end of the reply and could only ever read zero, which is what it
    # did: the conformance check reported 0 against the blob's 3. The
    # blob's own `speaker_mode` is the one to read.


class DeqSession:
    """Talks to one DEQ unit.

    It sends the unit's commands in the order the app sends them; you call
    `start()` and then the request methods; it depends on a `Transport` for
    the wire and on `deq_protocol` for the format.
    """

    def __init__(
        self,
        transport: Transport,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transactions_already_sent: int = 0,
    ) -> None:
        self.transport = transport
        self.timeout_seconds = timeout_seconds
        # Where the transaction ids start counting. A fresh session opens
        # at 1. A test that replays a captured reply gives the number of
        # transactions the capture had before it, so the ids line up.
        self._transaction_counter = transactions_already_sent
        # What a configuration read saw past the blob. A write has to send
        # it back; see `write_user_configuration`.
        self._configuration_trailing_bytes: bytes | None = None
        # Frames the unit pushed with nothing having asked for them. A
        # caller reads these to see what changed on the unit itself.
        self.notifications: list[Message] = []

    def next_transaction_id(self) -> bytes:
        """Returns the next transaction id, 8 bytes little-endian.

        The unit mirrors this back unchanged, which is how a reply is
        matched to its request.
        """
        self._transaction_counter += 1
        return self._transaction_counter.to_bytes(8, "little")

    def exchange(self, command_id: int, body: bytes = b"") -> Message:
        """Sends one command and returns the reply it answers with."""
        request = Message(
            direction=Direction.TO_DEVICE,
            command_id=command_id,
            transaction_id=self.next_transaction_id(),
            body=body,
        )
        self.transport.send_frame(encode_frame(request))
        reply = self._read_reply(request)
        self._check_status(reply)
        return reply

    def _read_reply(self, request: Message) -> Message:
        """Returns the reply to one request, skipping what it is not.

        The unit pushes notifications with nothing having asked for them --
        a real DEQ-S1000A2 sent one per step of the car's own volume knob
        on 2026-10-08. One of those arriving between a request and its
        reply is not an answer to anything, so it is recorded and passed
        over rather than compared against the request. Treating it as a
        reply raised `ReplyMismatchError` and broke the session, which is
        what turning the volume knob mid-request used to do.
        """
        while True:
            try:
                frame = self.transport.receive_frame(self.timeout_seconds)
            except TransportTimeout as caught_error:
                raise SessionTimeoutError(
                    f"no reply to command 0x{request.command_id:02x} "
                    f"within {self.timeout_seconds} seconds"
                ) from caught_error
            message = decode_frame(frame)
            if message.direction == Direction.NOTIFICATION:
                self.notifications.append(message)
                continue
            if self._answers_an_earlier_request(request, message):
                # A reply left over from a conversation this session did
                # not have. Reading it as an answer puts every later
                # request one reply out of step, which is what a car
                # session hit on 2026-10-08 when the Pi's gadget and this
                # backend both opened the link: "sent command 0x21, got a
                # reply to 0x15". Dropping it recovers instead.
                continue
            self._check_matches(request, message)
            return message

    def _answers_an_earlier_request(self, request: Message, reply: Message) -> bool:
        """True when a reply belongs to a request this session already sent.

        The transaction id says so: it counts up, so an id below the one
        in flight is stale. An id this session never sent at all is not
        stale but wrong, and `_check_matches` reports it.
        """
        if reply.transaction_id == request.transaction_id:
            return False
        if len(reply.transaction_id) != TRANSACTION_ID_BYTES:
            return False
        return int.from_bytes(reply.transaction_id, "little") < int.from_bytes(
            request.transaction_id, "little"
        )

    def _check_matches(self, request: Message, reply: Message) -> None:
        if reply.command_id != request.command_id:
            raise ReplyMismatchError(
                f"sent command 0x{request.command_id:02x}, "
                f"got a reply to 0x{reply.command_id:02x}"
            )
        if reply.transaction_id != request.transaction_id:
            raise ReplyMismatchError(
                f"command 0x{request.command_id:02x} got a reply carrying "
                f"transaction id {reply.transaction_id.hex()}, "
                f"not {request.transaction_id.hex()}"
            )

    def _check_status(self, reply: Message) -> None:
        """Raises when the unit reports a non-zero STATUS.

        The sync reply is checked like every other. An earlier version
        skipped it, which is exactly how a STATUS of -5 went unnoticed for
        two car sessions: the unit was refusing the open and saying so.
        """
        if len(reply.body) < STATUS_BYTES:
            return
        # Signed: the unit reports failure as a negative number, and -5 read
        # unsigned is 4294967291, which tells a reader nothing.
        status = int.from_bytes(
            reply.body[STATUS_OFFSET:STATUS_BYTES], "little", signed=True
        )
        if status != STATUS_OK:
            raise DeviceStatusError(reply.command_id, status)

    def start(self) -> None:
        """Runs the app's own connect sequence, then claims no audio.

        `STARTUP_STEPS` reads and changes nothing. The source mode is the
        one exception, and it is sent here rather than added to that table
        so the table keeps its property: every frame in it is a read.

        The mode has to be set because not setting it is not neutral. A Pi
        offering an audio function leaves the unit playing USB, and an
        empty USB input is silence -- measured in a car on 2026-10-08,
        where the audio returned within seconds of stopping the gadget.
        `THROUGH` hands the car's own audio back. Playing our own audio is
        a deliberate act on top of this, not the state a link starts in.

        The last frame is PLAY_READY, and it is what gives the car its
        audio. The real app ends every cold start with it, right after the
        mode write. A connect that stopped at the mode write left the car
        silent for as long as the Pi was attached, with the unit reporting
        THROUGH, a sane volume and a healthy link the whole time. Sent on
        its own in a car on 2026-10-11, the audio came back at once. It is
        not a write the unit stores: it carries no body, and the reply is
        a status only.
        """
        for command_id, body in STARTUP_STEPS:
            self.exchange(command_id, body)
        self.set_audio_source(DEFAULT_AUDIO_SOURCE)
        self.notify_play_ready()

    def send_keepalive(self) -> None:
        """Sends one keepalive. The app repeats this for the whole session."""
        self.exchange(COMMAND_KEEPALIVE)

    def read_device_identity(self) -> DeviceIdentity:
        """Returns the unit's firmware version and serial number."""
        version_reply = self.exchange(COMMAND_FIRMWARE_VERSION)
        identity_reply = self.exchange(COMMAND_DEVICE_IDENTITY)
        return DeviceIdentity(
            firmware_version=read_field(version_reply, offset=4, width=2),
            serial=read_text_field(identity_reply, offset=4, width=12),
        )

    def read_user_configuration(self) -> UserConfiguration:
        """Reads the unit's settings blob.

        The reply carries more than the blob. A real DEQ-S1000A2 answered
        with a 2032-byte body on 2026-10-08: four bytes of STATUS, the
        572-byte blob, and then 1456 bytes this app has no meaning for
        yet. So the blob has to be cut out rather than handed over whole,
        and `decode_blob` refuses the whole body -- with a message blaming
        NETWORK mode, which is misleading, since the unit was in STANDARD.
        """
        reply = self.exchange(COMMAND_READ_USER_CONFIGURATION)
        payload = reply.body[STATUS_BYTES:]
        # Keep the part this app does not decode, so a later write can hand
        # it back instead of guessing at it.
        self._configuration_trailing_bytes = payload[STANDARD_BLOB_BYTES:]
        return decode_blob(payload[:STANDARD_BLOB_BYTES])

    def write_user_configuration(self, configuration: UserConfiguration) -> None:
        """Writes the settings blob back to the unit.

        The unit wants the whole structure, not just the part this app
        decodes. `deq_commands.json` declares `0x08`'s USER_CONFIGURATION
        as 2028 bytes, which is exactly what `0x09` returns after its
        STATUS, and a real DEQ-S1000A2 refused a bare 572-byte blob with
        STATUS -5 on 2026-10-08.

        So the 572 bytes this app understands go in front, and the rest is
        carried through from the last read. Keeping what the unit sent is
        the point: those bytes have no known meaning here, and inventing
        them would write a guess into a car's audio processor. A write with
        no read before it pads with zeros, which is what this unit had in
        all 1456 of them.
        """
        self.exchange(
            COMMAND_WRITE_USER_CONFIGURATION,
            self.build_configuration_payload(configuration),
        )

    def build_configuration_payload(self, configuration: UserConfiguration) -> bytes:
        """Returns the 2028 bytes `0x08` wants: the blob, then the rest."""
        blob = encode_blob(configuration)
        trailing = self._configuration_trailing_bytes
        if trailing is None:
            trailing = bytes(CONFIGURATION_PAYLOAD_BYTES - len(blob))
        return blob + trailing

    def write_coefficients(self, config_id: int, configuration: bytes) -> None:
        """Sends one block of DSP coefficients.

        `deq_dsp` builds `configuration`. The unit answers a write with a
        short acknowledgement; it never echoes the block back.
        """
        self.exchange(
            COMMAND_WRITE_COEFFICIENTS,
            config_id.to_bytes(4, "little") + configuration,
        )

    def write_tuning(self, tuning: TuningData, layout: str = "standard") -> None:
        """Sends one profile's whole DSP state to the unit.

        Three blocks of command 0x05, each under its own CONFIG_ID: the
        equalizer, the time alignment, and the crossover. `deq_dsp` builds
        every one of them; this method only says which CONFIG_ID carries
        which and in what order.
        """
        self.write_equalizer(tuning)
        self.write_time_alignment(tuning)
        self.write_crossover(tuning, layout)

    def write_equalizer(self, tuning: TuningData) -> None:
        """Sends the 13 band gains, cancelled curve first."""
        plain_gains_db = selected_band_gains_db(tuning)
        cancelled_gains_db = cancelled_band_gains_db(tuning, plain_gains_db)
        self.write_coefficients(
            CONFIG_ID_EQUALIZER,
            build_equalizer_payload(cancelled_gains_db, plain_gains_db),
        )

    def write_time_alignment(self, tuning: TuningData) -> None:
        """Sends the per-speaker delays, as two blocks."""
        distances_mm = speaker_distances_mm(tuning)
        self.write_coefficients(
            CONFIG_ID_TIME_ALIGNMENT,
            build_time_alignment_payload(distances_mm),
        )

    def write_crossover(self, tuning: TuningData, layout: str) -> None:
        """Sends the crossover for one speaker layout.

        A profile carries only a front and a rear high-pass filter, which
        are slots 0 and 1. The other slots belong to the person, not to
        the preset: Pioneer sets the factory high-pass per car model and
        leaves the rest to its own Filter screen, which writes the unit's
        settings blob.

        So the unit's stored crossover fills the slots the profile says
        nothing about. Sending Pass for them instead would write identity
        biquads over a crossover somebody set, and the unit would then
        disagree with itself: the blob would still name a frequency and a
        slope while the audio ran unfiltered. A real unit read slot 2 at
        slope 3 and slot 3 at slope 4 on 2026-10-08, so this is a live
        setting on a real car and not a hypothetical one.
        """
        if layout not in CROSSOVER_CONFIG_IDS:
            raise ValueError(f"unknown crossover layout {layout!r}")
        cutoff_positions, slopes = crossover_slot_inputs(tuning)
        self.fill_unset_slots_from_unit(cutoff_positions, slopes)
        settings = crossover_slot_settings(layout, cutoff_positions, slopes)
        self.write_coefficients(
            CROSSOVER_CONFIG_IDS[layout],
            build_crossover_payload(layout, settings),
        )

    def fill_unset_slots_from_unit(
        self, cutoff_positions: list[int], slopes: list[FilterSlope]
    ) -> None:
        """Puts the unit's own crossover into the slots a profile omits.

        `crossover_slot_inputs` fills slots 0 and 1 from the profile and
        leaves the rest at Pass. This replaces those with what the unit
        already stores, so a push changes only what the profile speaks
        for. It edits both lists in place.

        The blob holds four slots, and the unit addresses five. The fifth
        has no stored value, so it stays as it came.
        """
        configuration = self.read_user_configuration()
        for slot in range(PROFILE_CROSSOVER_SLOT_COUNT, len(configuration.crossovers)):
            stored = configuration.crossovers[slot]
            cutoff_positions[slot] = stored.frequency
            slopes[slot] = FilterSlope(stored.slope)

    def select_eq_style(self, style_name: str) -> None:
        """Picks one of the unit's built-in EQ styles.

        No command carries a style as its own field. The style lives in the
        settings blob, as the preset index of the bank in use, so selecting
        one means reading the blob, changing that byte and writing it back.

        The unit keeps two banks, A and B, each with its own preset index,
        and `bank_in_use` says which one plays. The Pioneer app shows them
        as two more entries in its own picker, "Custom A" and "Custom B",
        because the app has nowhere else to keep a curve. This app does:
        a profile is a named curve, and there can be any number of them.
        So the banks are not a choice offered to a person here. They are
        only where a profile lands on the unit, and this writes whichever
        bank the unit already plays.
        """
        wire_value = EQ_STYLE.by_name(style_name).wire_value
        configuration = self.read_user_configuration()
        if configuration.bank_in_use == BANK_B:
            configuration.preset_index_b = wire_value
        else:
            configuration.preset_index_a = wire_value
        self.write_user_configuration(configuration)

    def select_live_simulation(self, mode_name: str) -> None:
        """Picks one of the unit's built-in live-simulation modes.

        Same story as the EQ style: it is `sound_field` in the blob, not a
        command of its own.
        """
        wire_value = LIVE_SIMULATION.by_name(mode_name).wire_value
        configuration = self.read_user_configuration()
        configuration.sound_field = wire_value
        self.write_user_configuration(configuration)

    def set_audio_source(self, source_name: str) -> None:
        """Picks which input the unit plays.

        This decides what comes out of the car's speakers while a session
        runs, and both answers were heard in a car on 2026-10-08:

            THROUGH (4)           the car's own audio
            SP_OTHER_SOURCE (5)   whatever this device writes over USB

        Both were measured with the Pi's audio function attached and a
        tone feeding, so an attached audio function does not take the
        car's audio -- an earlier version of this docstring said it did.
        THROUGH is the right default, and the connect sequence ends with
        it. The real app sets the mode explicitly too; `service/g` in the
        APK logs "ringing: setSourceMode(SourceMode.THROUGH)".

        One catch: the unit refuses a volume write with STATUS -6 while it
        holds THROUGH, and takes one on an OTHER mode. Set the mode first.
        """
        wire_value = AUDIO_SOURCE.by_name(source_name).wire_value
        self.exchange(COMMAND_SET_MODE, wire_value.to_bytes(4, "little", signed=True))

    def set_volume(self, volume_db: int) -> None:
        """Sets the master volume, in dB. The unit takes a signed value."""
        self.exchange(COMMAND_SET_VOLUME, volume_db.to_bytes(4, "little", signed=True))

    def set_mute_state(self, muted: bool) -> None:
        """Mutes or unmutes the unit.

        `deq_enums.json` names the values: SOUND_ON 1, SOUND_OFF 2. The
        command is 0x0f, the write partner of the 0x10 this reads back
        with `read_mute_state`.
        """
        wire_value = MUTE_STATE.by_name("SOUND_OFF" if muted else "SOUND_ON").wire_value
        self.exchange(COMMAND_SET_MUTE_STATE, wire_value.to_bytes(4, "little", signed=True))

    def read_mode(self) -> int:
        """Returns the source mode the unit holds, as a wire value.

        0x0c is a read: it carries no body and the unit answers with one
        field. The writing command, 0x0b, echoes the mode back too, which
        is how this was read before -- but that needs a write first, and
        a read does not.
        """
        return self._read_one_signed_field(COMMAND_GET_MODE)

    def read_volume(self) -> int:
        """Returns the master volume the unit holds, in dB."""
        return self._read_one_signed_field(COMMAND_GET_VOLUME)

    def read_mute_state(self) -> int:
        """Returns the mute state the unit holds, as a MUTE_STATE wire value.

        `deq_enums.json` names them: SOUND_ON 1, SOUND_OFF 2.
        """
        return self._read_one_signed_field(COMMAND_GET_MUTE_STATE)

    def read_driving_state(self) -> int:
        """Returns whether the unit thinks the car is moving."""
        return self._read_one_signed_field(COMMAND_GET_DRIVING_STATE)

    def _read_one_signed_field(self, command_id: int) -> int:
        """Sends a read with no body and returns its one 4-byte field.

        0x0c, 0x0e, 0x10 and 0x11 share a shape: an empty request, and a
        reply of STATUS and then one signed 32-bit value.
        """
        reply = self.exchange(command_id)
        return int.from_bytes(reply.body[4:8], "little", signed=True)

    def notify_play_ready(self) -> None:
        """Tells the unit this device is ready to play audio.

        0x1a, PLAY_READY_NOTIFICATION. The request carries no body at all,
        so there is nothing to guess: `deq_commands.json` gives it a
        16-byte payload, which is the header and the transaction id and
        nothing else. The reply is STATUS only.

        The real app sends it at the end of every cold start, right after
        the mode write, and `start` sends it for the same reason. It is
        what gives the car its audio: without it the car stayed silent for
        as long as the Pi was attached, and sent alone in a car on
        2026-10-11 it brought the audio back at once.
        """
        self.exchange(COMMAND_PLAY_READY_NOTIFICATION)

    def close(self) -> None:
        self.transport.close()


def selected_band_gains_db(tuning: TuningData) -> list[float]:
    """Returns the 13 band gains the profile has active.

    `foundationEq.eqs` holds one slot per channel group, and each slot
    stores several banks with `selectedBank` naming the live one. A profile
    in LR mode keeps one combined slot; the unit still wants one curve.
    """
    slots = tuning.foundationEq.eqs
    if slots == {}:
        raise ValueError("the profile carries no equalizer slot")
    slot = slots.get("LR") or next(iter(slots.values()))
    if slot.selectedBank >= len(slot.banks):
        raise ValueError(
            f"the profile selects bank {slot.selectedBank}, "
            f"but carries only {len(slot.banks)}"
        )
    return list(slot.banks[slot.selectedBank])


def cancelled_band_gains_db(
    tuning: TuningData, plain_band_gains_db: list[float]
) -> list[float]:
    """Returns the curve with the factory cancelling equalizer added in.

    The unit wants two curves: one with the cancelling equalizer applied
    and one without. A profile that has no cancelling data, or has it
    switched off, sends the same curve twice.
    """
    cancel = tuning.factoryCancel
    if not cancel.available or not cancel.enabled:
        return list(plain_band_gains_db)
    left = cancel.data.cancellingEQ.L
    return [
        plain_gain_db + cancel_gain_db
        for plain_gain_db, cancel_gain_db in zip(plain_band_gains_db, left)
    ]


def speaker_distances_mm(tuning: TuningData) -> list[int]:
    """Returns one distance per time-alignment slot, in millimetres.

    The profile stores centimetres, and the library works in whole
    millimetres. A layout with no subwoofer still fills the fifth slot, and
    it takes the farthest distance so the unit delays it by nothing.
    """
    distances_mm = [
        round(tuning.speakers[channel].timeAlignmentCm * 10)
        for channel in TIME_ALIGNMENT_CHANNELS
        if channel in tuning.speakers
    ]
    if distances_mm == []:
        raise ValueError("the profile names no speaker this unit drives")
    while len(distances_mm) < TIME_ALIGNMENT_SLOT_COUNT:
        distances_mm.append(max(distances_mm))
    return distances_mm


def crossover_slot_inputs(tuning: TuningData) -> tuple[list[int], list[FilterSlope]]:
    """Returns one cutoff position and one slope per filter slot.

    The unit addresses five slots. The profile carries a front and a rear
    high-pass filter, which are slots 0 and 1; it has no value for the
    other three, so they stay at Pass and the unit leaves them alone.

    Both profile fields are positions, not physical units: `cutoff_hpf` is
    an index into the 11-entry cutoff table and `slope_hpf` is the filter
    order. A factory preset stores 9 and 2 for its rear filter, which is
    200 Hz at 12 dB per octave.
    """
    cutoff_positions = [0] * CROSSOVER_SLOT_COUNT
    slopes = [FilterSlope.PASS] * CROSSOVER_SLOT_COUNT
    for slot, band in enumerate((tuning.filter.front, tuning.filter.rear)):
        cutoff_positions[slot] = int(band.cutoff_hpf)
        slopes[slot] = FilterSlope(int(band.slope_hpf))
    return cutoff_positions, slopes


def read_field(reply: Message, offset: int, width: int) -> int:
    """Reads one little-endian number out of a reply body.

    `offset` counts from the start of the body, so it is the field's
    payload offset minus 16. `deq_commands.json` gives the payload offset.
    """
    return int.from_bytes(reply.body[offset:offset + width], "little")


def read_text_field(reply: Message, offset: int, width: int) -> str:
    """Reads one fixed-width string out of a reply body.

    The unit pads a short string with zero bytes, and its serial numbers
    are plain ASCII.
    """
    raw = reply.body[offset:offset + width]
    return raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")
