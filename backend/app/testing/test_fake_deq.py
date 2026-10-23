"""Checks the fake DEQ against bytes a real DEQ sent.

The fake is worth having only if it answers the way the unit does. So the
load-bearing test here replays a captured request through it. It compares the
fake's reply with the unit's own, byte for byte. `conformance/flows.json` holds
those bytes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.deq_protocol import (
    Direction,
    Message,
    build_sync_body,
    decode_frame,
    encode_frame,
)
from app.deq_transport import TransportTimeout
from app.testing.fake_deq import FakeDeq, UnknownCommandError

CORPUS_PATH = Path(__file__).resolve().parents[3] / "conformance" / "flows.json"


def load_frame_flows() -> dict[str, dict]:
    corpus = json.loads(CORPUS_PATH.read_text())
    return {flow["name"]: flow for flow in corpus["flows"] if flow["kind"] == "frame"}


def test_the_fake_reproduces_the_real_units_reply():
    """The one check that makes this fake trustworthy.

    `frame-volume-request` and its reply are a matched pair from
    traffic with a physical DEQ-S1000A2: the same command id and the same
    transaction id. Feeding the request in has to produce the reply out.
    """
    flows = load_frame_flows()
    request_frame = bytes.fromhex(flows["frame-volume-request"]["bytesHex"])
    real_reply_hex = flows["frame-volume-reply"]["bytesHex"]

    fake = FakeDeq()
    fake.send_frame(request_frame)

    assert fake.receive_frame(1.0).hex() == real_reply_hex


def test_the_reply_length_field_is_the_requests_plus_four():
    flows = load_frame_flows()
    request = decode_frame(bytes.fromhex(flows["frame-volume-request"]["bytesHex"]))

    fake = FakeDeq()
    fake.send_frame(bytes.fromhex(flows["frame-volume-request"]["bytesHex"]))
    reply = decode_frame(fake.receive_frame(1.0))

    assert reply.declared_length == request.declared_length + 4


def test_a_volume_request_gets_its_own_value_back():
    """The capture pairs a -14 dB write with a reply carrying -14 back."""
    fake = FakeDeq()
    volume_body = bytes.fromhex("f2ffffff")
    fake.send_frame(build_request_frame(command_id=0x0D, body=volume_body))
    reply = decode_frame(fake.receive_frame(1.0))
    assert reply.body == bytes(4) + volume_body


# The sync reply a real DEQ-S1000A2 sent in the car on 2026-10-08, body
# only. STATUS 0, the 16-byte word, then volume -27, unmuted, parked.
REAL_SYNC_REPLY_BODY = bytes.fromhex(
    "000000003dd378e1054592964b2ede1fb9283b2b"
    "e5ffffff0000000000000000"
)


def test_a_sync_reply_matches_the_one_the_real_unit_sent():
    fake = FakeDeq(volume_db=-27, muted=False, driving=False)
    fake.send_frame(build_request_frame(command_id=0x00, body=build_sync_body()))
    assert decode_frame(fake.receive_frame(1.0)).body == REAL_SYNC_REPLY_BODY


def test_a_sync_with_no_body_is_refused_the_way_the_real_unit_refuses_it():
    # The real unit answered STATUS -5 and then ignored everything after.
    fake = FakeDeq()
    fake.send_frame(build_request_frame(command_id=0x00))
    reply = decode_frame(fake.receive_frame(1.0))
    assert reply.body == (-5).to_bytes(4, "little", signed=True)
    fake.send_frame(build_request_frame(command_id=0x03))
    with pytest.raises(TransportTimeout):
        fake.receive_frame(1.0)


def test_the_live_state_the_sync_reply_reports_is_tweakable():
    fake = FakeDeq(volume_db=-5, muted=True, driving=True)
    fake.send_frame(build_request_frame(command_id=0x00, body=build_sync_body()))
    body = decode_frame(fake.receive_frame(1.0)).body
    assert int.from_bytes(body[20:24], "little", signed=True) == -5
    assert int.from_bytes(body[24:28], "little") == 1
    assert int.from_bytes(body[28:32], "little") == 1


def test_a_status_fault_can_be_asked_for_by_command():
    fake = FakeDeq(status_by_command={0x03: -7})
    fake.send_frame(build_request_frame(command_id=0x03))
    reply = decode_frame(fake.receive_frame(1.0))
    assert reply.body == (-7).to_bytes(4, "little", signed=True)


def test_the_unit_can_be_told_to_go_silent_after_one_command():
    fake = FakeDeq(silent_after={0x03})
    fake.send_frame(build_request_frame(command_id=0x03))
    assert decode_frame(fake.receive_frame(1.0)).command_id == 0x03
    fake.send_frame(build_request_frame(command_id=0x04))
    with pytest.raises(TransportTimeout):
        fake.receive_frame(1.0)


def test_an_unmeasured_large_command_raises_rather_than_answering_zeros():
    """A zero-filled reply would let a test pass against behaviour that no real
    unit showed. The protocol work lost days to that."""
    fake = FakeDeq()
    with pytest.raises(UnknownCommandError, match="no reply rule"):
        fake.send_frame(build_request_frame(command_id=0x7E, body=bytes(64)))


def test_a_silent_fake_never_answers():
    fake = FakeDeq(answers=False)
    fake.send_frame(build_request_frame(command_id=0x02))
    with pytest.raises(TransportTimeout):
        fake.receive_frame(0.01)


def test_a_serial_longer_than_the_field_raises():
    fake = FakeDeq(serial="THIRTEEN_CHAR")
    with pytest.raises(ValueError, match="does not fit"):
        fake.send_frame(build_request_frame(command_id=0x04))


def build_request_frame(command_id: int, body: bytes = b"") -> bytes:
    return encode_frame(
        Message(
            direction=Direction.TO_DEVICE,
            command_id=command_id,
            transaction_id=(1).to_bytes(8, "little"),
            body=body,
        )
    )


CAPTURES_PATH = Path(__file__).resolve().parent / "captures"

# The volume the real unit held through the car session on 2026-10-08. It
# is in all three captured replies below, so a fake that reports anything
# else cannot reproduce them.
REAL_UNIT_VOLUME_DB = -37

# STATUS the real unit answered a volume write with while a tone fed. Every
# other refusal on record is -5, so this one is its own code.
REAL_VOLUME_REFUSAL_STATUS = -6


def read_capture(name: str) -> str:
    return (CAPTURES_PATH / name).read_text().strip()


def test_the_fake_reproduces_the_real_units_mode_reply():
    """0x0b answers with four fields, and this test holds the real unit's
    answer.

    Captured in the car on 2026-10-08 at transaction id 11, when the backend
    set THROUGH: MODE 4, volume -37 dB, mute 1, not driving. The generic echo
    rule answered with MODE alone, and no unit ever did that.

    The mute field is a boolean (`b/f/x` reads it with `b/g/a.b([B)Z`), so 1
    means muted. The unit was muted then, and THROUGH still played the car.
    """
    fake = FakeDeq(volume_db=REAL_UNIT_VOLUME_DB, muted=True)
    request = encode_frame(
        Message(
            direction=Direction.TO_DEVICE,
            command_id=0x0B,
            transaction_id=(11).to_bytes(8, "little"),
            body=(4).to_bytes(4, "little", signed=True),
        )
    )

    fake.send_frame(request)

    assert fake.receive_frame(1.0).hex() == read_capture(
        "20261008_set_mode_reply.hex"
    )


def test_the_fake_reproduces_the_real_units_answer_to_a_mute():
    """The unit took a mute write of 2 with STATUS 0 and answered 1.

    Captured at transaction id 13. The field is a boolean, so 1 means muted:
    the write worked. This capture was read as "the unit ignores 0x0f" until
    2026-10-15, when the APK showed the boolean.
    """
    fake = FakeDeq()
    request = encode_frame(
        Message(
            direction=Direction.TO_DEVICE,
            command_id=0x0F,
            transaction_id=(13).to_bytes(8, "little"),
            body=(2).to_bytes(4, "little", signed=True),
        )
    )

    fake.send_frame(request)

    assert fake.receive_frame(1.0).hex() == read_capture(
        "20261008_mute_state_reply.hex"
    )


def test_the_fake_reproduces_the_real_units_volume_refusal():
    """A refused volume write keeps the unit's own volume.

    Captured at transaction id 12: STATUS -6 and -37 dB, after the backend
    asked for -10 dB while a tone fed.
    """
    fake = FakeDeq(
        volume_db=REAL_UNIT_VOLUME_DB,
        status_by_command={0x0D: REAL_VOLUME_REFUSAL_STATUS},
    )
    request = encode_frame(
        Message(
            direction=Direction.TO_DEVICE,
            command_id=0x0D,
            transaction_id=(12).to_bytes(8, "little"),
            body=(-10).to_bytes(4, "little", signed=True),
        )
    )

    fake.send_frame(request)

    assert fake.receive_frame(1.0).hex() == read_capture(
        "20261008_volume_refusal_reply.hex"
    )


def test_a_mute_write_of_0_plays_again():
    fake = FakeDeq(muted=True)
    request = encode_frame(
        Message(
            direction=Direction.TO_DEVICE,
            command_id=0x0F,
            transaction_id=(14).to_bytes(8, "little"),
            body=(0).to_bytes(4, "little", signed=True),
        )
    )

    fake.send_frame(request)
    fake.receive_frame(1.0)

    assert fake.muted is False


def test_the_fake_reproduces_the_real_units_level_block():
    """`0x06` CONFIG_ID 0 returns the level block after the CONFIG_ID.

    Captured at transaction id 10 of the car's cold start on 2026-10-08.
    """
    fake = FakeDeq()
    request = encode_frame(
        Message(
            direction=Direction.TO_DEVICE,
            command_id=0x06,
            transaction_id=(10).to_bytes(8, "little"),
            body=(0).to_bytes(4, "little"),
        )
    )

    fake.send_frame(request)

    assert fake.receive_frame(1.0).hex() == read_capture(
        "20261008_level_configuration_reply.hex"
    )
