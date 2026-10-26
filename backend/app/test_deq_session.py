"""Checks the session against a DEQ that answers like the real one."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.deq_blob import (
    STANDARD_BLOB_BYTES,
    CrossoverSetting as BlobCrossoverSetting,
    UserConfiguration,
)
from app.deq_dsp import (
    WIDE_BAND_COUNT,
    speaker_level_byte,
    FilterSlope,
    build_crossover_payload,
    build_equalizer_payload,
    convert_wide_bands_to_equalizer_bands,
    crossover_slot_settings,
)
from app.deq_protocol import Direction, Message, decode_frame, encode_frame
from app.deq_protocol import build_set_timeout_interval_body, build_sync_body
from app.deq_session import (
    CONFIGURATION_PAYLOAD_BYTES,
    COMMAND_KEEPALIVE,
    COMMAND_PLAY_READY_NOTIFICATION,
    COMMAND_SET_MODE,
    COMMAND_SET_TIMEOUT_INTERVAL,
    COMMAND_SYNC,
    CONFIG_ID_CROSSOVER_NETWORK,
    CONFIG_ID_CROSSOVER_STANDARD,
    CONFIG_ID_EQUALIZER,
    CONFIG_ID_LEVELS,
    CONFIG_ID_TIME_ALIGNMENT,
    STARTUP_STEPS,
    DeqSession,
    DeviceStatusError,
    ReplyMismatchError,
    SessionTimeoutError,
    cancelled_band_gains_db,
    muted_speakers,
    selected_band_gains_db,
    speaker_distances_mm,
)
from app.eq_data import TuningData
from app.deq_transport import TransportTimeout
from app.testing.fake_deq import FAKE_SERIAL, FakeDeq
from app.unit_crossover import UnsupportedSpeakerModeError


def test_start_sends_the_apps_own_connect_order():
    """The reads come in the app's own order, and the source mode follows
    them. `STARTUP_STEPS` stays a table of reads only, which is what makes
    it safe to replay against a unit."""
    fake = FakeDeq()
    DeqSession(fake).start()
    expected = [command_id for command_id, _ in STARTUP_STEPS] + [
        COMMAND_SET_MODE,
        COMMAND_PLAY_READY_NOTIFICATION,
    ]
    assert fake.command_order == expected


# Every command that changes the unit's settings. A connect must not send
# one of these. 0x16 erases the unit's own crash log, 0x1f is a SET, and
# the rest write tuning, coefficients, volume or mute.
WRITING_COMMANDS = (0x16, 0x1F, 0x05, 0x19, 0x0D, 0x0F)

# COMMAND_SET_MODE, 0x0b, is a write, and the list above leaves it out on
# purpose. To skip it is not neutral. A Pi that offers an audio function leaves
# the unit on USB, and an empty USB input is silence. A car measured on
# 2026-10-08 had no audio for as long as the gadget ran. So a connect sets
# THROUGH, which hands the car's own audio back. It is the one thing a connect
# changes, and it changes it to the state a person expects.


def test_start_sends_no_command_that_changes_the_units_tuning():
    """A connect must not touch tuning, coefficients, volume or mute, and
    must not erase the unit's crash log."""
    fake = FakeDeq()
    DeqSession(fake).start()
    sent = set(fake.command_order)
    assert sent.isdisjoint(WRITING_COMMANDS)


def test_start_hands_the_cars_own_audio_back_through_the_dsp():
    """Connecting must not cost a person their radio. The unit plays
    whatever source it holds, so the mode has to be said out loud. The
    default is CAR_SOURCE (3), because THROUGH most likely skips the DSP."""
    fake = FakeDeq()

    DeqSession(fake).start()

    assert sent_mode(fake) == 3


def test_start_sets_the_mode_it_is_given():
    fake = FakeDeq()

    DeqSession(fake).start("THROUGH")

    assert sent_mode(fake) == 4


def sent_mode(fake: FakeDeq) -> int:
    mode_request = next(
        one.request for one in fake.exchanges
        if one.request.command_id == COMMAND_SET_MODE
    )
    return int.from_bytes(mode_request.body, "little", signed=True)


def test_start_ends_with_play_ready_after_the_mode_write():
    """The car stayed silent whenever the Pi attached, with the unit reporting
    THROUGH and a healthy link, until the session sent PLAY_READY. The real app
    sends it last, right after the mode write, so the order is part of the
    behaviour."""
    fake = FakeDeq()

    DeqSession(fake).start()

    assert fake.command_order[-2:] == [COMMAND_SET_MODE, COMMAND_PLAY_READY_NOTIFICATION]


def test_start_opens_with_the_sync_body_the_unit_requires():
    # An empty body here is what a real DEQ refused with STATUS -5.
    fake = FakeDeq()
    DeqSession(fake).start()
    first = fake.exchanges[0].request
    assert first.command_id == COMMAND_SYNC
    assert first.body == build_sync_body()


def test_start_sets_the_timeout_interval_the_app_sends():
    fake = FakeDeq()
    DeqSession(fake).start()
    timeout_request = next(
        one.request for one in fake.exchanges
        if one.request.command_id == COMMAND_SET_TIMEOUT_INTERVAL
    )
    assert timeout_request.body == build_set_timeout_interval_body()
    # The app sends it second, right after the open.
    assert fake.command_order[1] == COMMAND_SET_TIMEOUT_INTERVAL


def test_each_request_carries_a_new_transaction_id():
    fake = FakeDeq()
    session = DeqSession(fake)
    session.send_keepalive()
    session.send_keepalive()
    first, second = (one.request.transaction_id for one in fake.exchanges)
    assert first != second


def test_the_unit_mirrors_the_transaction_id_back():
    """The capture shows every reply carrying the request's own id."""
    fake = FakeDeq()
    DeqSession(fake).send_keepalive()
    exchange = fake.exchanges[0]
    assert exchange.reply.transaction_id == exchange.request.transaction_id


def test_read_device_identity_reports_what_the_unit_says():
    fake = FakeDeq(firmware_version=0x0310)
    identity = DeqSession(fake).read_device_identity()
    assert identity.firmware_version == 0x0310
    assert identity.serial == FAKE_SERIAL


def test_a_written_configuration_reads_back():
    fake = FakeDeq()
    session = DeqSession(fake)
    configuration = UserConfiguration(bank_in_use=1, equalizer_enabled=1)
    configuration.bank_a_gains_db[0] = 6.0

    session.write_user_configuration(configuration)
    read_back = session.read_user_configuration()

    assert read_back.bank_in_use == 1
    assert read_back.equalizer_enabled == 1
    assert read_back.bank_a_gains_db[0] == pytest.approx(6.0)


def test_a_coefficient_write_is_acknowledged_not_echoed():
    """A 2100-byte write gets a 24-byte reply. Echoing the block back is
    what the real app refuses with `[Code:601]`."""
    fake = FakeDeq()
    session = DeqSession(fake)

    session.write_coefficients(config_id=13, configuration=bytes(2080))

    reply = fake.exchanges[0].reply
    assert fake.exchanges[0].request.payload_length == 2100
    assert reply.payload_length == 24


def test_volume_sends_a_signed_value():
    """The capture's own volume frame carries -14 as `f2ffffff`."""
    fake = FakeDeq()
    DeqSession(fake).set_volume(-14)
    assert fake.exchanges[0].request.body == bytes.fromhex("f2ffffff")


def test_write_tuning_sends_four_blocks_under_the_right_config_ids():
    """Each CONFIG_ID's payload size has to match the width the APK's own
    field enum declares for it, or the unit refuses the frame."""
    fake = FakeDeq()
    DeqSession(fake).write_tuning(load_factory_tuning())

    # A push also reads the unit's own blob, to keep the crossover slots a
    # profile says nothing about. Only the coefficient writes matter here.
    coefficient_writes = [one for one in fake.exchanges if one.request.command_id == 0x05]
    sent = [
        (int.from_bytes(one.request.body[:4], "little"), one.request.payload_length)
        for one in coefficient_writes
    ]
    assert sent == [
        (CONFIG_ID_LEVELS, 48),
        (CONFIG_ID_EQUALIZER, 2100),
        (CONFIG_ID_TIME_ALIGNMENT, 52),
        (CONFIG_ID_CROSSOVER_STANDARD, 204),
    ]


def _sent_crossover(fake: FakeDeq) -> bytes:
    """Returns the body of the last crossover write, after its CONFIG_ID."""
    return [
        one
        for one in fake.exchanges
        if one.request.command_id == 0x05
        and int.from_bytes(one.request.body[:4], "little")
        in (CONFIG_ID_CROSSOVER_STANDARD, CONFIG_ID_CROSSOVER_NETWORK)
    ][-1].request.body[4:]


def _standard_payload(cutoff_positions: list[int], slopes: list[int]) -> bytes:
    return build_crossover_payload(
        "standard",
        crossover_slot_settings(
            "standard", cutoff_positions, [FilterSlope(slope) for slope in slopes]
        ),
    )


def test_a_push_keeps_the_units_subwoofer_low_pass():
    """A profile carries a front and a rear high-pass filter, and nothing else.
    The subwoofer's low pass belongs to the person, who sets it on the unit's
    own filter screen.

    The car's mode, STANDARD_FL_FR_RL_RR_SW, sends that low pass in slot 4.
    These are the values a real unit held on 2026-10-08: the rear subwoofer
    entry at 5 and 3, which this mode does not use, and the subwoofer at 3
    and 4, which is 50 Hz at 24 dB per octave."""
    fake = FakeDeq()
    fake.configuration.crossovers[2] = BlobCrossoverSetting(frequency=5, slope=3)
    fake.configuration.crossovers[3] = BlobCrossoverSetting(frequency=3, slope=4)
    tuning = load_factory_tuning()

    DeqSession(fake).write_tuning(tuning)

    front, rear = tuning.filter.front, tuning.filter.rear
    assert _sent_crossover(fake) == _standard_payload(
        [int(front.cutoff_hpf), int(rear.cutoff_hpf), 0, 0, 3],
        [int(front.slope_hpf), int(rear.slope_hpf), 0, 0, 4],
    )


def test_a_push_without_a_subwoofer_leaves_slot_four_on_pass():
    """STANDARD_FL_FR_RL_RR drives no subwoofer, so the app sends no low
    pass, whatever the blob still stores for one."""
    fake = FakeDeq()
    fake.configuration.speaker_mode = 2
    fake.configuration.crossovers[3] = BlobCrossoverSetting(frequency=3, slope=4)
    tuning = load_factory_tuning()

    DeqSession(fake).write_tuning(tuning)

    front, rear = tuning.filter.front, tuning.filter.rear
    assert _sent_crossover(fake) == _standard_payload(
        [int(front.cutoff_hpf), int(rear.cutoff_hpf), 0, 0, 0],
        [int(front.slope_hpf), int(rear.slope_hpf), 0, 0, 0],
    )


def test_a_network_mode_push_raises():
    """The blob reader knows only the STANDARD form, so a NETWORK unit's
    crossover has no map yet. A push must say so, not guess."""
    fake = FakeDeq()
    fake.configuration.speaker_mode = 7
    with pytest.raises(UnsupportedSpeakerModeError):
        DeqSession(fake).write_crossover(load_factory_tuning())


def test_a_push_sends_the_profiles_levels_and_keeps_the_units_subwoofer():
    """A profile names four speakers. The car's unit holds +10 dB on its
    subwoofer and a level per source mode, and a push keeps both."""
    fake = FakeDeq()
    tuning = load_factory_tuning()

    DeqSession(fake).write_tuning(tuning)

    level_write = [
        one
        for one in fake.exchanges
        if one.request.command_id == 0x05
        and int.from_bytes(one.request.body[:4], "little") == CONFIG_ID_LEVELS
    ][-1]
    block = level_write.request.body[4:]
    assert block[:4] == fake.level_configuration[:4]
    assert list(block[4:8]) == [
        speaker_level_byte(tuning.speakers[name].levelDB) & 0xFF
        for name in ("FL", "FR", "RL", "RR")
    ]
    assert block[8] == 10
    assert block[20:] == fake.level_configuration[20:]


def test_a_push_still_sends_the_profiles_own_high_pass_filters():
    """The unit's stored filters fill the other slots, and must not reach
    back into the two the profile owns. The profile's fields are positions:
    9 and 2 mean 200 Hz at 12 dB per octave, not 9 Hz."""
    fake = FakeDeq()
    fake.configuration.crossovers[0] = BlobCrossoverSetting(frequency=4, slope=4)
    fake.configuration.crossovers[1] = BlobCrossoverSetting(frequency=4, slope=4)
    tuning = load_factory_tuning()
    tuning.filter.front.cutoff_hpf = 7
    tuning.filter.front.slope_hpf = 1
    tuning.filter.rear.cutoff_hpf = 9
    tuning.filter.rear.slope_hpf = 2

    DeqSession(fake).write_crossover(tuning)

    assert _sent_crossover(fake) == _standard_payload([7, 9, 0, 0, 0], [1, 2, 0, 0, 0])


def test_the_equalizer_block_matches_what_deq_dsp_builds():
    """The session must not transform the gains on the way through."""
    tuning = load_factory_tuning()
    fake = FakeDeq()
    DeqSession(fake).write_equalizer(tuning)

    gains_db = selected_band_gains_db(tuning)
    expected = build_equalizer_payload(cancelled_band_gains_db(tuning, gains_db), gains_db)
    assert fake.exchanges[0].request.body[4:] == expected


def test_a_profile_with_no_cancelling_data_sends_the_same_curve_twice():
    tuning = load_factory_tuning()
    assert not tuning.factoryCancel.enabled
    gains_db = selected_band_gains_db(tuning)
    assert cancelled_band_gains_db(tuning, gains_db) == gains_db


def test_distances_come_through_in_millimetres_with_five_slots():
    """The profile stores centimetres for four speakers. The library wants
    millimetres for five."""
    tuning = load_factory_tuning()
    distances_mm = speaker_distances_mm(tuning)
    assert len(distances_mm) == 5
    assert distances_mm[0] == round(tuning.speakers["FL"].timeAlignmentCm * 10)
    assert distances_mm[4] == max(distances_mm)


def test_a_profile_selecting_a_bank_it_does_not_have_raises():
    tuning = load_factory_tuning()
    slot = tuning.foundationEq.eqs["LR"]
    slot.selectedBank = len(slot.banks)
    with pytest.raises(ValueError, match="selects bank"):
        selected_band_gains_db(tuning)


def test_a_31_band_bank_reaches_the_unit_as_13_bands():
    """The unit's own tune is 31-band. The app converts such a bank before
    it builds the equalizer, and so does the session."""
    tuning = load_factory_tuning()
    slot = tuning.foundationEq.eqs["LR"]
    wide_gains_db = [float(band % 7) - 3 for band in range(WIDE_BAND_COUNT)]
    slot.banks[slot.selectedBank] = wide_gains_db

    gains_db = selected_band_gains_db(tuning)

    assert gains_db == convert_wide_bands_to_equalizer_bands(wide_gains_db)
    fake = FakeDeq()
    DeqSession(fake).write_equalizer(tuning)
    assert fake.exchanges[0].request.body[4:] == build_equalizer_payload(
        cancelled_band_gains_db(tuning, gains_db), gains_db
    )


def load_factory_tuning() -> TuningData:
    """Returns one bundled factory preset, as shipped."""
    preset_path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "presets"
        / "mazda"
        / "tuning_preset_model_mazda_3_carrozzeria.json"
    )
    return TuningData.model_validate(json.loads(preset_path.read_text()))


def test_a_reply_to_another_command_raises():
    session = DeqSession(ReplyingTransport(command_id_shift=1))
    with pytest.raises(ReplyMismatchError, match="got a reply to"):
        session.send_keepalive()


def test_a_reply_carrying_another_transaction_id_raises():
    session = DeqSession(ReplyingTransport(transaction_id_shift=1))
    with pytest.raises(ReplyMismatchError, match="transaction id"):
        session.send_keepalive()


def test_a_silent_unit_times_out():
    session = DeqSession(FakeDeq(answers=False), timeout_seconds=0.01)
    with pytest.raises(SessionTimeoutError, match="no reply"):
        session.send_keepalive()


def test_a_refused_request_raises_with_its_status():
    session = DeqSession(ReplyingTransport(status=5))
    with pytest.raises(DeviceStatusError) as caught:
        session.send_keepalive()
    assert caught.value.status == 5
    assert caught.value.command_id == COMMAND_KEEPALIVE


def test_close_releases_the_link():
    fake = FakeDeq()
    DeqSession(fake).close()
    assert fake.closed


class ReplyingTransport:
    """Answers every request, with one chosen thing wrong.

    It replies to every request it receives. You set one shift or status in the
    constructor. It depends on `deq_protocol` to build the reply. These shifts
    exist to trip the session's own checks.
    """

    def __init__(
        self,
        command_id_shift: int = 0,
        transaction_id_shift: int = 0,
        status: int = 0,
    ) -> None:
        self.command_id_shift = command_id_shift
        self.transaction_id_shift = transaction_id_shift
        self.status = status
        self._pending_reply: bytes | None = None
        self.closed = False

    def send_frame(self, frame: bytes) -> None:
        request = decode_frame(frame)
        transaction_id = (
            int.from_bytes(request.transaction_id, "little") + self.transaction_id_shift
        )
        self._pending_reply = encode_frame(
            Message(
                direction=Direction.FROM_DEVICE,
                command_id=request.command_id + self.command_id_shift,
                transaction_id=transaction_id.to_bytes(8, "little"),
                body=self.status.to_bytes(4, "little"),
            )
        )

    def receive_frame(self, timeout_seconds: float) -> bytes:
        if self._pending_reply is None:
            raise TransportTimeout("nothing to send")
        frame = self._pending_reply
        self._pending_reply = None
        return frame

    def close(self) -> None:
        self.closed = True


class ReplayingTransport:
    """Answers one command with one recorded frame.

    It replays what a real unit sent, and you give it the frame. It depends on
    nothing. `FakeDeq` cannot serve this test. It answers `0x09` with only the
    572 bytes the blob needs, and that hid this bug.
    """

    def __init__(self, reply_frame: bytes) -> None:
        self.reply_frame = reply_frame
        self.sent: list[bytes] = []

    def send_frame(self, frame: bytes) -> None:
        self.sent.append(frame)

    def receive_frame(self, timeout_seconds: float) -> bytes:
        return self.reply_frame

    def close(self) -> None:
        pass


REAL_REPLY_PATH = (
    Path(__file__).parent / "testing" / "captures"
    / "20261008_user_configuration_reply.hex"
)


def test_the_blob_is_cut_out_of_a_real_units_longer_reply():
    """A real DEQ-S1000A2 answered 0x09 with a 2032-byte body on 2026-10-08.
    The body held four bytes of STATUS, the 572-byte blob, and 1456 bytes that
    have no meaning for this app yet.

    `decode_blob` fails on the whole body, and `check_real_deq.py` found that
    against the unit. The values asserted here are the car's own tune, read
    from that capture.
    """
    reply_frame = bytes.fromhex(REAL_REPLY_PATH.read_text().strip())
    transport = ReplayingTransport(reply_frame)
    # The recorded reply carries transaction id 9, so the session has to
    # reach that id for the reply to match the request it answers.
    session = DeqSession(transport, transactions_already_sent=8)

    configuration = session.read_user_configuration()

    assert configuration.version == 3
    assert configuration.speaker_mode == 3
    assert configuration.listening_position == 5
    assert configuration.band_count == 31


def test_a_configuration_write_sends_the_whole_structure_the_unit_wants():
    """A real DEQ-S1000A2 refused a bare 572-byte blob with STATUS -5 on
    2026-10-08. `0x08` declares a 2028-byte USER_CONFIGURATION, which is
    what `0x09` returns after its STATUS.
    """
    fake = FakeDeq()
    session = DeqSession(fake)
    configuration = UserConfiguration(bank_in_use=1)

    session.write_user_configuration(configuration)

    written = decode_frame(fake.sent_frames[-1])
    assert len(written.body) == CONFIGURATION_PAYLOAD_BYTES


def test_a_write_hands_back_the_bytes_the_read_did_not_decode():
    """Those 1456 bytes have no known meaning in this app, so a write must
    carry through what the unit sent rather than invent them. On the car's
    own unit they were all zero, but that is this unit's state and not a
    rule to encode.
    """
    recognisable = bytes([0xAB]) * (CONFIGURATION_PAYLOAD_BYTES - STANDARD_BLOB_BYTES)
    session = DeqSession(FakeDeq())
    session._configuration_trailing_bytes = recognisable

    payload = session.build_configuration_payload(UserConfiguration())

    assert len(payload) == CONFIGURATION_PAYLOAD_BYTES
    assert payload[STANDARD_BLOB_BYTES:] == recognisable


def test_a_write_with_no_read_before_it_pads_with_zeros():
    """The meaning of those bytes stays unknown until a read sees them, and the
    car's unit had zeros in all of them."""
    session = DeqSession(FakeDeq())

    payload = session.build_configuration_payload(UserConfiguration())

    assert len(payload) == CONFIGURATION_PAYLOAD_BYTES
    assert set(payload[STANDARD_BLOB_BYTES:]) == {0}


class PushesNotificationFirst:
    """Pushes one notification, then answers, as a real unit does.

    The unit sends a notification whenever something changes on it, even while
    a request is in flight. You give it the frame to push. It depends on
    nothing. `FakeDeq` answers one request with one reply and never pushes, so
    it cannot show this.
    """

    def __init__(self, notification_frame: bytes) -> None:
        self.queue = [notification_frame]

    def send_frame(self, frame: bytes) -> None:
        request = decode_frame(frame)
        self.queue.append(
            encode_frame(
                Message(
                    direction=Direction.FROM_DEVICE,
                    command_id=request.command_id,
                    transaction_id=request.transaction_id,
                    body=bytes(4),
                )
            )
        )

    def receive_frame(self, timeout_seconds: float) -> bytes:
        return self.queue.pop(0)

    def close(self) -> None:
        pass


VOLUME_NOTIFICATION_FRAME = bytes.fromhex(
    "f000400600000001000300000009000000040000000000000e0e0f0f0f0f0f0ff7"
)


def test_a_notification_between_a_request_and_its_reply_is_not_a_mismatch():
    """A real DEQ-S1000A2 pushed one of these per step of the car's own
    volume knob on 2026-10-08. One arriving mid-exchange is not an answer
    to anything, and treating it as one raised `ReplyMismatchError` and
    broke the session.
    """
    transport = PushesNotificationFirst(VOLUME_NOTIFICATION_FRAME)
    session = DeqSession(transport)

    reply = session.exchange(COMMAND_KEEPALIVE)

    assert reply.command_id == COMMAND_KEEPALIVE


def test_a_skipped_notification_is_kept_not_thrown_away():
    """It says what changed on the unit, which is the only way to learn
    about a change nothing asked for."""
    transport = PushesNotificationFirst(VOLUME_NOTIFICATION_FRAME)
    session = DeqSession(transport)

    session.exchange(COMMAND_KEEPALIVE)

    assert len(session.notifications) == 1
    pushed = session.notifications[0]
    assert pushed.direction == Direction.NOTIFICATION
    assert int.from_bytes(pushed.body, "little", signed=True) == -18


def test_setting_the_audio_source_sends_the_apk_s_own_wire_value():
    """THROUGH keeps a car audible while this app holds the link. Its wire
    value is 4, and not its ordinal 5. The constructor of `SourceMode` is
    (name, ordinal, wireValue), and the wrong argument selects SP_OTHER_SOURCE
    instead.
    """
    fake = FakeDeq()
    session = DeqSession(fake)

    session.set_audio_source("THROUGH")

    sent = decode_frame(fake.sent_frames[-1])
    assert sent.command_id == COMMAND_SET_MODE
    assert int.from_bytes(sent.body, "little", signed=True) == 4


def test_an_unknown_audio_source_name_is_refused():
    """A wrong name must not reach the unit as some other mode."""
    session = DeqSession(FakeDeq())

    with pytest.raises(KeyError):
        session.set_audio_source("NOT_A_SOURCE_MODE")


class ReplaysAStaleReplyFirst:
    """Hands back one reply from a conversation this session did not have.

    The Pi's gadget and the backend both opened the link in a car on
    2026-10-08. That left a reply in flight for a request that this session
    never sent. Every later request then read the answer to the previous one.
    You give it the stale reply. It answers everything after that correctly.
    """

    def __init__(self, stale_reply: bytes) -> None:
        self.queue = [stale_reply]

    def send_frame(self, frame: bytes) -> None:
        request = decode_frame(frame)
        self.queue.append(
            encode_frame(
                Message(
                    direction=Direction.FROM_DEVICE,
                    command_id=request.command_id,
                    transaction_id=request.transaction_id,
                    body=bytes(4),
                )
            )
        )

    def receive_frame(self, timeout_seconds: float) -> bytes:
        return self.queue.pop(0)

    def close(self) -> None:
        pass


def test_a_reply_to_an_earlier_request_is_dropped_not_read_as_this_one():
    """Two openers on one link leave a reply in flight. A real session read it
    as an answer and fell one reply out of step. The connect failed with "sent
    command 0x21, got a reply to 0x15"."""
    stale = encode_frame(
        Message(
            direction=Direction.FROM_DEVICE,
            command_id=0x15,
            transaction_id=(1).to_bytes(8, "little"),
            body=bytes(4),
        )
    )
    transport = ReplaysAStaleReplyFirst(stale)
    session = DeqSession(transport, transactions_already_sent=4)

    reply = session.exchange(COMMAND_KEEPALIVE)

    assert reply.command_id == COMMAND_KEEPALIVE
    assert int.from_bytes(reply.transaction_id, "little") == 5


def test_a_reply_carrying_an_id_this_session_never_sent_is_still_an_error():
    """Dropping a stale reply must not swallow a genuinely wrong one: an
    id ahead of the request is not a leftover, it is a mismatch."""
    ahead = encode_frame(
        Message(
            direction=Direction.FROM_DEVICE,
            command_id=COMMAND_KEEPALIVE,
            transaction_id=(99).to_bytes(8, "little"),
            body=bytes(4),
        )
    )
    transport = ReplaysAStaleReplyFirst(ahead)
    session = DeqSession(transport)

    with pytest.raises(ReplyMismatchError, match="transaction id"):
        session.exchange(COMMAND_KEEPALIVE)


class OneFieldTransport:
    """Answers every request with STATUS 0 and one 4-byte value.

    The APK gives this reply layout for 0x14 and 0x1c. No real unit
    answered either read so far, so `FakeDeq` has no rule for them. This
    transport tests the decoding only, and makes no claim about the value.
    """

    def __init__(self, value: int) -> None:
        self.value = value
        self.requests: list[Message] = []
        self.replies: list[bytes] = []

    def send_frame(self, frame: bytes) -> None:
        request = decode_frame(frame)
        self.requests.append(request)
        body = bytes(4) + self.value.to_bytes(4, "little", signed=True)
        self.replies.append(
            encode_frame(
                Message(
                    direction=Direction.FROM_DEVICE,
                    command_id=request.command_id,
                    transaction_id=request.transaction_id,
                    body=body,
                )
            )
        )

    def receive_frame(self, timeout_seconds: float) -> bytes:
        return self.replies.pop(0)

    def close(self) -> None:
        pass


def test_the_speaker_mute_read_sends_0x14_and_returns_its_field():
    transport = OneFieldTransport(5)

    value = DeqSession(transport).read_speaker_mute_states()

    assert transport.requests[0].command_id == 0x14
    assert transport.requests[0].body == b""
    assert value == 5


def test_the_system_mute_read_sends_0x1c_and_keeps_the_sign():
    transport = OneFieldTransport(-1)

    value = DeqSession(transport).read_system_mute_state()

    assert transport.requests[0].command_id == 0x1C
    assert value == -1

def test_speaker_mute_bits_follow_the_apps_masks():
    """`b/g/e$f$a` gives one bit per speaker pair, and a set bit mutes it."""
    assert muted_speakers(0) == []
    assert muted_speakers(0x01 | 0x10) == ["FL_HL", "SW"]
    assert muted_speakers(0x3F) == ["FL_HL", "FR_HR", "RL_ML", "RR_MR", "SW", "RSW"]

