"""Drives the conversation with the DEQ.

`deq_protocol` says what one message looks like. This module says which
messages to send, in what order, and what a reply has to satisfy before the app
believes it.

The order comes from the real app. `USB_CAPTURE_NOTES.md` records the sequence
that the Sound & Tune app sends on connect. The notes read it from a session
that reached a working connected state. Traffic captured from a physical unit
shows the same order. The app is the authority on it, so `STARTUP_STEPS` copies
that order and invents none.

The roles are the reverse of the capture. There the app is the host and the DEQ
answers. This app takes the host's place, so it sends those commands and reads
the DEQ's replies.

Every reply must satisfy three rules. Captured traffic between the app and a
real DEQ-S1000A2 shows all three:

- the reply's command id equals the request's
- the reply's transaction id equals the request's, byte for byte
- STATUS, the first four body bytes, is zero

A reply that breaks one of these rules does not answer our request. The app's
own error codes come from the same checks. The app raises `[Code:601]` when a
reply's content does not fit the request it answers.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.deq_blob import (
    BANK_A,
    CrossoverSetting as StoredFilter,
    BANK_B,
    STANDARD_BLOB_BYTES,
    UserConfiguration,
    decode_blob,
    encode_blob,
)
from app.deq_enums import AUDIO_SOURCE, EQ_STYLE, LIVE_SIMULATION
from app.deq_dsp import (
    LEVEL_BLOCK_BYTES,
    TIME_ALIGNMENT_SLOT_COUNT,
    WIDE_BAND_COUNT,
    SpeakerLevel,
    build_crossover_payload,
    build_equalizer_payload,
    build_level_payload,
    build_time_alignment_payload,
    convert_wide_bands_to_equalizer_bands,
    crossover_slot_settings,
)
from app.unit_crossover import STORED_FRONT, STORED_REAR, crossover_slot_inputs
from app.deq_protocol import (
    CONFIG_ID_BYTES,
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
# `fragment/playground/i$d`, which is an enum of (name, ordinal, wire value).
# The names below come from that enum. Each one agrees with the request and
# reply fields that `deq_commands.json` carries for the same id. Read the enum
# before you invent a name. Four of the names here were wrong at one time. One
# of them sent a read at the wrong command for three weeks.
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
COMMAND_GET_SPEAKER_MUTE_STATE = 0x14
COMMAND_CRASH_REPORT = 0x15
COMMAND_SYSTEM_ERROR_FLAGS = 0x17
COMMAND_SELF_SAVE_CONFIGURATION_ENABLE = 0x19
COMMAND_PLAY_READY_NOTIFICATION = 0x1A
COMMAND_GET_SYSTEM_MUTE_STATE = 0x1C
COMMAND_SET_USB_CONDITIONER_TABLE = 0x1F
COMMAND_GET_USB_CONDITIONER_TABLE = 0x20
COMMAND_SET_TIMEOUT_INTERVAL = 0x21

# This program used the name `COMMAND_SYNC` for 0x00 before anyone read the
# APK's own enum. The name stays, so nothing that imports it breaks.
COMMAND_SYNC = COMMAND_CONNECT

# Which CONFIG_ID carries which block of command 0x05. The APK holds the
# answer. The dispatch in `b/e/ab` maps each id to the field enum that declares
# its CONFIGURATION size. The sizes settle the mapping.
#
#   id 0  -> af$a$l, 0x1c = 28 bytes, the levels
#   id 10 -> af$a$g, 0x20 = 32 bytes, two 16-byte time-alignment blocks
#   id 11 -> af$a$e, 0xb8 = 184 bytes, the standard crossover
#   id 12 -> af$a$f, 0x1a8 = 424 bytes, the network crossover
#   id 13 -> af$a$h, 0x82c = 2080 bytes, the equalizer
#
# The 2080 and the two crossover sizes match `conformance/flows.json` byte for
# byte. So a test checks the mapping, and nobody assumes it.
CONFIG_ID_LEVELS = 0
CONFIG_ID_TIME_ALIGNMENT = 10
CONFIG_ID_CROSSOVER_STANDARD = 11
CONFIG_ID_CROSSOVER_NETWORK = 12
CONFIG_ID_EQUALIZER = 13

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

# How many bytes the USER_CONFIGURATION field of `0x08` carries, from
# `deq_commands.json`. It is the whole structure. This app decodes the first
# 572. `0x09` returns the same count after its STATUS. A real unit refused a
# bare 572-byte write with STATUS -5.
CONFIGURATION_PAYLOAD_BYTES = 2028

# How long to wait for one reply. The app's own keepalive runs about every nine
# seconds. So a reply that takes longer than this timeout means a dead link.
DEFAULT_TIMEOUT_SECONDS = 5.0

# Which input the unit plays once a link is up, when nobody chose one.
#
# CAR_SOURCE plays the car's own audio through the unit's DSP. THROUGH
# most likely skips the DSP. The app's code shows this, and the car has
# not confirmed it yet (2026-10-14):
#
# - The app picks THROUGH only while a phone call rings, and during a
#   calibration measurement (`service/g`, "ringing:
#   setSourceMode(SourceMode.THROUGH)").
# - Otherwise its start restores the mode that the person last chose.
# - Its level block (0x05 CONFIG_ID 0) has a level for each source mode
#   except THROUGH.
#
# An emulated cold start sent THROUGH on 2026-10-08. That app was a fresh
# install with no mode to restore. A drive on 2026-10-14 pushed four
# profiles and two EQ styles in THROUGH, and none of them changed the
# sound much.
DEFAULT_AUDIO_SOURCE = "CAR_SOURCE"

# The order the app sends on connect. Each entry is a command id and the body
# to send with it. A body of `b""` means the command carries nothing but its
# transaction id.
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
    # This sequence is the app's own, minus every command that writes. The app
    # also sends 0x16, 0x1f, 0x05 (twice), 0x19, 0x0d, 0x0b and 0x1a. All of
    # those change the unit. 0x16 erases its crash log, and 0x1f is a SET. The
    # rest write tuning, coefficients, volume or mode. A connect must read and
    # change nothing, so this list sends none of them. An earlier version of
    # this list sent three of them by mistake: 0x16, 0x1f and
    # COMMAND_SELF_SAVE_CONFIGURATION_ENABLE.
)


class SessionError(Exception):
    """The conversation with the unit failed."""


class ReplyMismatchError(SessionError):
    """A reply did not answer the request that this session sent."""


class SessionTimeoutError(SessionError):
    """The unit did not answer in time."""


class DeviceStatusError(SessionError):
    """The unit answered, and said no.

    `status` is the value it reported. A non-zero value means it refused the
    request. The app shows the same condition as a communication error.
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
    # This class has no speaker mode, though `deq_commands.json` declares one.
    # The APK says `0x04` answers with 40 payload bytes and SPEAKER_MODE at
    # offset 36. A real DEQ-S1000A2 answered with 24 on 2026-10-08: four of
    # STATUS, twelve of ASCII serial, eight zero. So the field lies past the
    # end of the reply and can only read zero. It did read zero: the
    # conformance check reported 0 against the blob's 3. Read the blob's own
    # `speaker_mode` instead.


class DeqSession:
    """Talks to one DEQ unit.

    It sends the unit's commands in the order the app sends them. You call
    `start()` and then the request methods. It depends on a `Transport` for the
    wire and on `deq_protocol` for the format.
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
        # What a configuration read saw past the blob. A write has to send it
        # back. See `write_user_configuration`.
        self._configuration_trailing_bytes: bytes | None = None
        # Frames that the unit pushed with no request for them. A caller reads
        # these to see what changed on the unit itself.
        self.notifications: list[Message] = []

    def next_transaction_id(self) -> bytes:
        """Returns the next transaction id, 8 bytes little-endian.

        The unit mirrors this id back unchanged. The id lets a reply match its
        request.
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
        """Returns the reply to one request, and skips every other frame.

        The unit pushes notifications that nothing asked for. A real
        DEQ-S1000A2 sent one per step of the car's own volume knob on
        2026-10-08. If one of those arrives between a request and its reply, it
        answers nothing. So this method records it and passes over it, and does
        not compare it with the request. An earlier version took it as a reply.
        That raised `ReplyMismatchError` and broke the session whenever the
        volume knob turned mid-request.
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
                # A reply left over from a conversation that this session did
                # not have. If the session reads it as an answer, every later
                # request falls one reply out of step. A car session hit that
                # on 2026-10-08. The Pi's gadget and this backend both opened
                # the link, and the error read: "sent command 0x21, got a reply
                # to 0x15". The session drops the stale reply and recovers.
                continue
            self._check_matches(request, message)
            return message

    def _answers_an_earlier_request(self, request: Message, reply: Message) -> bool:
        """True when a reply belongs to a request this session already sent.

        The transaction id tells. It counts up, so an id below the one in
        flight is stale. An id that this session never sent is wrong, and
        `_check_matches` reports it.
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

        This method checks the sync reply like every other. An earlier version
        skipped it. That let a STATUS of -5 go unnoticed for two car sessions:
        the unit refused the open and said so.
        """
        if len(reply.body) < STATUS_BYTES:
            return
        # Signed: the unit reports failure as a negative number. Read as
        # unsigned, -5 is 4294967291, which tells a reader nothing.
        status = int.from_bytes(
            reply.body[STATUS_OFFSET:STATUS_BYTES], "little", signed=True
        )
        if status != STATUS_OK:
            raise DeviceStatusError(reply.command_id, status)

    def start(self, source_name: str = DEFAULT_AUDIO_SOURCE) -> None:
        """Runs the app's own connect sequence, then sets the source mode.

        `STARTUP_STEPS` reads and changes nothing. The source mode is the one
        exception. This method sends it, and the table does not hold it. So the
        table keeps its property: every frame in it is a read.

        The mode has to be set, because an unset mode has an effect too. A Pi
        that offers an audio function leaves the unit on USB, and an empty USB
        input is silence. A car on 2026-10-08 showed this: the audio came back
        within seconds of a stop of the gadget. CAR_SOURCE and THROUGH both
        hand the car's own audio back. Our own audio needs a deliberate step on
        top of this. A link does not start in that state.

        The last frame is PLAY_READY, and it gives the car its audio. The real
        app ends every cold start with it, right after the mode write. A
        connect that stopped at the mode write left the car silent for as long
        as the Pi stayed attached. The unit reported THROUGH, a sane volume and
        a healthy link the whole time. In a car on 2026-10-11, PLAY_READY sent
        on its own brought the audio back at once. The unit stores nothing from
        this frame. It carries no body, and the reply is a status only.
        """
        for command_id, body in STARTUP_STEPS:
            self.exchange(command_id, body)
        self.set_audio_source(source_name)
        self.notify_play_ready()

    def send_keepalive(self) -> None:
        """Sends one keepalive. The app repeats it for the whole session."""
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

        The reply carries more than the blob. A real DEQ-S1000A2 answered with
        a 2032-byte body on 2026-10-08. The body held four bytes of STATUS, the
        572-byte blob, and then 1456 bytes that have no meaning for this app
        yet. So this method cuts the blob out and does not hand the body over
        whole. `decode_blob` refuses the whole body. Its message blames NETWORK
        mode, which misleads, because the unit was in STANDARD.
        """
        reply = self.exchange(COMMAND_READ_USER_CONFIGURATION)
        payload = reply.body[STATUS_BYTES:]
        # Keep the part this app does not decode, so a later write can hand
        # it back instead of guessing at it.
        self._configuration_trailing_bytes = payload[STANDARD_BLOB_BYTES:]
        return decode_blob(payload[:STANDARD_BLOB_BYTES])

    def write_user_configuration(self, configuration: UserConfiguration) -> None:
        """Writes the settings blob back to the unit.

        The unit wants the whole structure, and not only the part this app
        decodes. `deq_commands.json` declares the USER_CONFIGURATION of `0x08`
        as 2028 bytes. `0x09` returns the same 2028 bytes after its STATUS. A
        real DEQ-S1000A2 refused a bare 572-byte blob with STATUS -5 on
        2026-10-08.

        So the 572 bytes this app understands go in front. The rest comes
        through from the last read. The write keeps what the unit sent on
        purpose. Those bytes have no known meaning here, and an invented value
        would write a guess into a car's audio processor. A write with no read
        before it pads with zeros. This unit had zeros in all 1456 of them.
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

        `deq_dsp` builds `configuration`. The unit answers a write with a short
        acknowledgement. It never echoes the block back.
        """
        self.exchange(
            COMMAND_WRITE_COEFFICIENTS,
            config_id.to_bytes(4, "little") + configuration,
        )

    def write_tuning(self, tuning: TuningData) -> None:
        """Sends one profile's whole DSP state to the unit.

        Four blocks of command 0x05, each under its own CONFIG_ID: the
        levels, the equalizer, the time alignment, and the crossover.
        `deq_dsp` builds every one of them. This method only says which
        CONFIG_ID carries which, and in what order. The levels go first, as
        in the app's own full push.

        The app sends a fifth block, CONFIG_ID 9. It holds RearSWEnabled and
        three zeros. The app sends it only when the speaker mode changes
        between STANDARD and NETWORK. A profile push never changes that mode,
        so this method does not send it.
        """
        self.write_levels(tuning)
        self.write_equalizer(tuning)
        self.write_time_alignment(tuning)
        self.write_crossover(tuning)

    def read_level_configuration(self) -> bytes:
        """Returns the level block that the unit holds now, 28 bytes.

        `0x06` answers with STATUS, the CONFIG_ID it read, and then the
        block.
        """
        reply = self.exchange(
            COMMAND_READ_CONFIGURATION_TABLE,
            build_get_opal_configuration_body(CONFIG_ID_LEVELS),
        )
        block_offset = STATUS_BYTES + CONFIG_ID_BYTES
        block = reply.body[block_offset:block_offset + LEVEL_BLOCK_BYTES]
        if len(block) != LEVEL_BLOCK_BYTES:
            raise SessionError(
                f"the unit returned a level block of {len(block)} bytes, "
                f"not {LEVEL_BLOCK_BYTES}"
            )
        return block

    def write_levels(self, tuning: TuningData) -> None:
        """Sends the speaker levels, the fader and the balance.

        The block also holds a level per source mode and a subwoofer level.
        A profile has no value for them, so they come from the unit. The car's
        unit held a subwoofer level of +10 dB on 2026-10-08. A block built
        from zeros would turn it off.
        """
        self.write_coefficients(
            CONFIG_ID_LEVELS,
            build_level_payload(
                self.read_level_configuration(),
                profile_speaker_levels(tuning),
                fader=int(tuning.faderBalance.fader),
                balance=int(tuning.faderBalance.balance),
            ),
        )

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

    def write_crossover(self, tuning: TuningData) -> None:
        """Sends the crossover: the profile's two filters, the unit's others.

        A profile carries only a front and a rear high-pass filter. Pioneer
        sets them per car model. It leaves the other filters, such as the
        subwoofer's low pass, to its own Filter screen, which writes the
        unit's settings blob.

        So the unit's stored filters fill everything the profile does not
        name. Pass in their place would write identity biquads over a
        crossover that somebody set. The unit would then disagree with
        itself: the blob would still name a frequency and a slope while the
        audio ran unfiltered. The car's unit stores a subwoofer low pass at
        50 Hz and 24 dB per octave (read 2026-10-08).

        The speaker mode in the blob decides which stored filter goes into
        which slot. `unit_crossover.py` holds that map.
        """
        configuration = self.read_user_configuration()
        self.write_stored_crossover(
            configuration.speaker_mode,
            with_profile_filters(configuration.crossovers, profile_filters(tuning)),
        )

    def write_stored_filter(
        self,
        stored_index: int,
        stored_filter: StoredFilter,
        playing_profile_filters: tuple[StoredFilter, StoredFilter] | None,
    ) -> UserConfiguration:
        """Changes one stored filter on the unit, and makes the DSP play it.

        The blob write keeps the filter across a power cycle, and the
        crossover write makes it audible now. The crossover keeps the front
        and rear filters of the profile that plays, because a push sent
        those and the blob may still hold older ones. With no profile, the
        blob's own front and rear filters go out.
        """
        configuration = self.read_user_configuration()
        configuration.crossovers[stored_index] = stored_filter
        self.write_user_configuration(configuration)
        stored_filters = list(configuration.crossovers)
        if playing_profile_filters is not None:
            stored_filters = with_profile_filters(stored_filters, playing_profile_filters)
        self.write_stored_crossover(configuration.speaker_mode, stored_filters)
        return configuration

    def write_stored_crossover(
        self, speaker_mode: int, stored_filters: list[StoredFilter]
    ) -> None:
        """Sends the crossover that a speaker mode and its stored filters give."""
        layout, cutoff_positions, slopes = crossover_slot_inputs(
            speaker_mode, stored_filters
        )
        settings = crossover_slot_settings(layout, cutoff_positions, slopes)
        self.write_coefficients(
            CROSSOVER_CONFIG_IDS[layout],
            build_crossover_payload(layout, settings),
        )

    def select_eq_style(self, style_name: str) -> None:
        """Picks one of the unit's built-in EQ styles.

        No command carries a style as its own field. The style lives in the
        settings blob, as the preset index of the bank in use. So a selection
        reads the blob, changes that byte and writes the blob back.

        The unit keeps two banks, A and B, each with its own preset index.
        `bank_in_use` says which one plays. The Pioneer app shows them as two
        more entries in its own picker, "Custom A" and "Custom B". The app has
        nowhere else to keep a curve. This app has such a place: a profile is a
        named curve, and a person can keep any number of them. So this app does
        not offer the banks as a choice. A bank is only where a profile lands
        on the unit, and this method writes to the bank that the unit already
        plays.
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

        The EQ style works the same way. The mode is `sound_field` in the blob,
        and no command of its own carries it.
        """
        wire_value = LIVE_SIMULATION.by_name(mode_name).wire_value
        configuration = self.read_user_configuration()
        configuration.sound_field = wire_value
        self.write_user_configuration(configuration)

    def set_audio_source(self, source_name: str) -> None:
        """Picks which input the unit plays.

        The mode decides what comes out of the car's speakers while a session
        runs. A person heard both answers in a car on 2026-10-08:

            THROUGH (4)           the car's own audio
            SP_OTHER_SOURCE (5)   whatever this device writes over USB

        Both measurements had the Pi's audio function attached and a tone
        playing. So an attached audio function does not take the car's audio.
        An earlier version of this docstring said that it did. THROUGH most
        likely skips the DSP, so the connect sequence uses CAR_SOURCE unless
        the person chose a mode (see `DEFAULT_AUDIO_SOURCE`).

        One catch: the unit refuses a volume write with STATUS -6 while it
        holds THROUGH, and takes one on an OTHER mode. Set the mode first.
        """
        wire_value = AUDIO_SOURCE.by_name(source_name).wire_value
        self.exchange(COMMAND_SET_MODE, wire_value.to_bytes(4, "little", signed=True))

    def use_custom_bank_a(self) -> None:
        """Puts the unit's own EQ style on Custom, in bank A.

        This app designs the whole curve itself and sends it as coefficients:
        the car profile's curve plus the chosen EQ. The Pioneer app does the
        same for its own styles. It asks its player library for a style's
        curve (`PMGPlayer.getMultiBandEqualizerPreset`) and adds it before the
        design. So the unit's stored style only names what plays. Custom in
        bank A says "the app's own curve". The blob is written only when it
        says something else.
        """
        configuration = self.read_user_configuration()
        custom = EQ_STYLE.by_name("CUSTOM").wire_value
        if configuration.bank_in_use == BANK_A and configuration.preset_index_a == custom:
            return
        configuration.bank_in_use = BANK_A
        configuration.preset_index_a = custom
        self.write_user_configuration(configuration)

    def set_volume(self, volume_db: int) -> None:
        """Sets the master volume, in dB. The unit takes a signed value."""
        self.exchange(COMMAND_SET_VOLUME, volume_db.to_bytes(4, "little", signed=True))

    def set_mute_state(self, muted: bool) -> None:
        """Mutes or unmutes the unit, with command 0x0f.

        The wire carries a boolean, not the MUTE_STATE enum: 1 mutes and 0
        plays. The app's request builder `b/e/aa` turns SOUND_OFF into true
        through `b/g/e$d.a` and writes it with `b/g/a.b(Z)`. The Pioneer app's
        mute button sent 1 and then 0 on the tablet (2026-09-29).

        An earlier version sent the enum values, 2 and 1. So its "unmute"
        sent 1, which mutes.
        """
        self.exchange(COMMAND_SET_MUTE_STATE, int(muted).to_bytes(4, "little", signed=True))

    def read_mode(self) -> int:
        """Returns the source mode the unit holds, as a wire value.

        0x0c is a read. It carries no body, and the unit answers with one
        field. The writing command, 0x0b, also echoes the mode back. An earlier
        version read the mode that way, but that needs a write first, and a
        read does not.
        """
        return self._read_one_signed_field(COMMAND_GET_MODE)

    def read_volume(self) -> int:
        """Returns the master volume the unit holds, in dB."""
        return self._read_one_signed_field(COMMAND_GET_VOLUME)

    def read_mute_state(self) -> int:
        """Returns what the unit says about mute: 1 muted, 0 playing.

        The wire carries a boolean, as for the write. The app turns it into
        its enum with `b/g/e$d.a(Z)`: true is SOUND_OFF.
        """
        return self._read_one_signed_field(COMMAND_GET_MUTE_STATE)

    def read_driving_state(self) -> int:
        """Returns whether the unit thinks the car is moving."""
        return self._read_one_signed_field(COMMAND_GET_DRIVING_STATE)

    def read_speaker_mute_states(self) -> int:
        """Returns the SPEAKER_MUTE_STATES field of 0x14, as the unit sends it.

        The APK names the field and gives its width, 4 bytes. No real unit
        answered this read so far, so this method does not interpret the value.
        `check_real_deq.py` reads it, so the next session with the car shows
        what it holds.
        """
        return self._read_one_signed_field(COMMAND_GET_SPEAKER_MUTE_STATE)

    def read_system_mute_state(self) -> int:
        """Returns the MUTE_STATE field of 0x1c, as the unit sends it.

        The unit keeps a second mute, apart from 0x10. It ignores a write of
        0x0f, so this one may be the mute it obeys. No real unit answered this
        read so far.
        """
        return self._read_one_signed_field(COMMAND_GET_SYSTEM_MUTE_STATE)

    def _read_one_signed_field(self, command_id: int) -> int:
        """Sends a read with no body and returns its one 4-byte field.

        0x0c, 0x0e, 0x10, 0x11, 0x14 and 0x1c share a shape: an empty request, and a
        reply of STATUS and then one signed 32-bit value.
        """
        reply = self.exchange(command_id)
        return int.from_bytes(reply.body[4:8], "little", signed=True)

    def notify_play_ready(self) -> None:
        """Tells the unit this device is ready to play audio.

        0x1a, PLAY_READY_NOTIFICATION. The request carries no body at all, so
        nothing needs a guess. `deq_commands.json` gives it a 16-byte payload,
        which is the header and the transaction id and nothing else. The reply
        is STATUS only.

        The real app sends it at the end of every cold start, right after the
        mode write. `start` sends it for the same reason: it gives the car its
        audio. Without it the car stayed silent for as long as the Pi stayed
        attached. Sent alone in a car on 2026-10-11, it brought the audio back
        at once.
        """
        self.exchange(COMMAND_PLAY_READY_NOTIFICATION)

    def close(self) -> None:
        self.transport.close()


def selected_band_gains_db(tuning: TuningData) -> list[float]:
    """Returns the 13 band gains the profile has active.

    `foundationEq.eqs` holds one slot per channel group. Each slot stores
    several banks, and `selectedBank` names the live one. A profile in LR mode
    keeps one combined slot. The unit still wants one curve.

    A 31-band bank, as the unit's own tune holds, goes through the app's
    31-to-13 conversion first.
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
    gains_db = list(slot.banks[slot.selectedBank])
    if len(gains_db) == WIDE_BAND_COUNT:
        return convert_wide_bands_to_equalizer_bands(gains_db)
    return gains_db


def cancelled_band_gains_db(
    tuning: TuningData, plain_band_gains_db: list[float]
) -> list[float]:
    """Returns the curve with the factory cancelling equalizer added in.

    The unit wants two curves: one with the cancelling equalizer applied and
    one without. A profile with no cancelling data, or with the cancelling
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


def profile_speaker_levels(tuning: TuningData) -> dict[str, SpeakerLevel]:
    """Returns the level of each speaker that the profile names."""
    return {
        name: SpeakerLevel(level_db=speaker.levelDB, extended_db=speaker.levelDBExtended)
        for name, speaker in tuning.speakers.items()
    }


def profile_filters(tuning: TuningData) -> tuple[StoredFilter, StoredFilter]:
    """Returns a profile's front and rear high-pass filters, as the blob stores them.

    Both hold positions and not physical units: an index into the 11-entry
    cutoff table and the filter order. A factory preset stores 9 and 2 for
    its rear filter, which is 200 Hz at 12 dB per octave.
    """
    return tuple(
        StoredFilter(frequency=int(band.cutoff_hpf), slope=int(band.slope_hpf))
        for band in (tuning.filter.front, tuning.filter.rear)
    )


def with_profile_filters(
    stored_filters: list[StoredFilter],
    front_and_rear: tuple[StoredFilter, StoredFilter],
) -> list[StoredFilter]:
    """Returns the stored filters with a profile's front and rear put in."""
    combined = list(stored_filters)
    combined[STORED_FRONT], combined[STORED_REAR] = front_and_rear
    return combined


def read_field(reply: Message, offset: int, width: int) -> int:
    """Reads one little-endian number out of a reply body.

    `offset` counts from the start of the body, so it is the field's
    payload offset minus 16. `deq_commands.json` gives the payload offset.
    """
    return int.from_bytes(reply.body[offset:offset + width], "little")


def read_text_field(reply: Message, offset: int, width: int) -> str:
    """Reads one fixed-width string out of a reply body.

    The unit pads a short string with zero bytes. Its serial numbers are plain
    ASCII.
    """
    raw = reply.body[offset:offset + width]
    return raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")
