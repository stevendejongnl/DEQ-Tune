"""Runs the shared conformance corpus against the Python implementation.

`conformance/flows.json` holds every flow the DEQ needs, with the exact bytes
that the Pioneer Sound & Tune app produces for it. Those bytes come from the
app's own code on a running device. So the app is the oracle, and this code is
the thing under test.

The backend owns the link to the unit, so this runner is the only one.
`app/testing/test_fake_deq.py` uses the same corpus from the other side. It
checks that the fake unit the tests talk to answers a captured request with the
real unit's own captured reply.

This runner checks both directions wherever a flow can be read back, so a drift
in either direction fails.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.deq_blob import decode_blob, encode_blob
from app.deq_dsp import (
    FilterSlope,
    build_crossover_payload,
    build_equalizer_payload,
    build_time_alignment_block,
    crossover_slot_settings,
)
from app.deq_protocol import Direction, Message, decode_frame, encode_frame

CORPUS_PATH = Path(__file__).resolve().parents[2] / "conformance" / "flows.json"
CORPUS = json.loads(CORPUS_PATH.read_text())
FLOWS = CORPUS["flows"]

# The maker the app calls, and the speaker layout this code calls it.
MAKER_LAYOUTS = {
    "MakeSpeakerFilterStandardMode": "standard",
    "MakeSpeakerFilterStandardRearMode": "standard_rear",
    "MakeSpeakerFilterNetworkMode": "network",
}

# The 11 cutoff positions, under both the names the app's enum gives them.
# A position means the low frequency or fifty times it, decided by the
# speaker's role, so the name alone does not fix the frequency.
CUTOFF_POSITIONS = {
    "FREQUENCY_25HZ": 0, "FREQUENCY_31_5HZ": 1, "FREQUENCY_40HZ": 2,
    "FREQUENCY_50HZ": 3, "FREQUENCY_63HZ": 4, "FREQUENCY_80HZ": 5,
    "FREQUENCY_100HZ": 6, "FREQUENCY_125HZ": 7, "FREQUENCY_160HZ": 8,
    "FREQUENCY_200HZ": 9, "FREQUENCY_250HZ": 10,
    "FREQUENCY_1_25KHZ": 0, "FREQUENCY_1_6KHZ": 1, "FREQUENCY_2KHZ": 2,
    "FREQUENCY_2_5KHZ": 3, "FREQUENCY_3_15KHZ": 4, "FREQUENCY_4KHZ": 5,
    "FREQUENCY_5kHZ": 6, "FREQUENCY_6_3KHZ": 7, "FREQUENCY_8KHZ": 8,
    "FREQUENCY_10KHZ": 9, "FREQUENCY_12_5KHZ": 10,
}
# The two ranges are separate series. See `crossover_cutoff_hz`.

SLOPES = {
    "SLOPE_PASS": FilterSlope.PASS,
    "SLOPE_6DB": FilterSlope.SLOPE_6,
    "SLOPE_12DB": FilterSlope.SLOPE_12,
    "SLOPE_18DB": FilterSlope.SLOPE_18,
    "SLOPE_24DB": FilterSlope.SLOPE_24,
}

def flows_of(kind: str) -> list[dict]:
    return [flow for flow in FLOWS if flow["kind"] == kind]


def flow_id(flow: dict) -> str:
    return flow["name"]


def test_the_corpus_covers_every_flow_kind() -> None:
    kinds = {flow["kind"] for flow in FLOWS}
    assert kinds == {"frame", "equalizer", "crossover", "timeAlignment", "blob"}


def test_every_flow_has_a_named_oracle() -> None:
    for flow in FLOWS:
        assert flow["oracle"] in {"android-library", "android-codec", "device-capture"}


@pytest.mark.parametrize("flow", flows_of("frame"), ids=flow_id)
def test_a_frame_flow_writes_the_bytes_the_app_wrote(flow: dict) -> None:
    message = Message(
        direction=Direction(flow["input"]["direction"]),
        command_id=flow["input"]["commandId"],
        transaction_id=bytes.fromhex(flow["input"]["transactionIdHex"]),
        body=bytes.fromhex(flow["input"]["bodyHex"]),
    )
    assert encode_frame(message).hex() == flow["bytesHex"]


@pytest.mark.parametrize("flow", flows_of("frame"), ids=flow_id)
def test_a_frame_flow_reads_back_to_its_own_input(flow: dict) -> None:
    message = decode_frame(bytes.fromhex(flow["bytesHex"]))
    assert int(message.direction) == flow["input"]["direction"]
    assert message.command_id == flow["input"]["commandId"]
    assert message.transaction_id.hex() == flow["input"]["transactionIdHex"]
    assert message.body.hex() == flow["input"]["bodyHex"]


@pytest.mark.parametrize("flow", flows_of("equalizer"), ids=flow_id)
def test_an_equalizer_flow_writes_the_bytes_the_app_wrote(flow: dict) -> None:
    payload = build_equalizer_payload(
        flow["input"]["cancelledGainsDb"], flow["input"]["plainGainsDb"]
    )
    assert payload.hex() == flow["bytesHex"]


@pytest.mark.parametrize("flow", flows_of("crossover"), ids=flow_id)
def test_a_crossover_flow_writes_the_bytes_the_app_wrote(flow: dict) -> None:
    layout = MAKER_LAYOUTS[flow["input"]["maker"]]
    settings = crossover_slot_settings(
        layout,
        [CUTOFF_POSITIONS[raw["cutoff"]] for raw in flow["input"]["slots"]],
        [SLOPES[raw["slope"]] for raw in flow["input"]["slots"]],
    )
    assert build_crossover_payload(layout, settings).hex() == flow["bytesHex"]


@pytest.mark.parametrize("flow", flows_of("timeAlignment"), ids=flow_id)
def test_a_time_alignment_flow_writes_the_bytes_the_app_wrote(flow: dict) -> None:
    payload = build_time_alignment_block(flow["input"]["distancesMm"])
    assert payload.hex() == flow["bytesHex"]


@pytest.mark.parametrize("flow", flows_of("blob"), ids=flow_id)
def test_a_blob_flow_reads_and_writes_what_the_app_does(flow: dict) -> None:
    # The app read the input bytes and wrote these out. This code must agree
    # on both steps, so a round trip here is the same check the app passed.
    blob = bytes.fromhex(flow["input"]["bytesHex"])
    assert encode_blob(decode_blob(blob)).hex() == flow["bytesHex"]
