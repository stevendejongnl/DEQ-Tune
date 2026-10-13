"""Tests for the simulated DEQ a developer can change while it runs."""

from __future__ import annotations

import pytest

from app.deq_protocol import (
    Direction,
    Message,
    build_sync_body,
    decode_frame,
    encode_frame,
)
from app.deq_simulator_state import DeqSimulatorState
from app.deq_simulator_transport import DeqSimulator
from app.deq_transport import TransportTimeout


def request_frame(command_id: int, body: bytes = b"") -> bytes:
    return encode_frame(
        Message(
            direction=Direction.TO_DEVICE,
            command_id=command_id,
            transaction_id=(1).to_bytes(8, "little"),
            body=body,
        )
    )


def simulator_reading(state: DeqSimulatorState) -> DeqSimulator:
    """A simulator that takes the given state in place of its state file.

    The seam is the loader, so no test writes a file or stubs a global.
    """
    return DeqSimulator(load_state_function=lambda path: state)


def sync_reply_body(simulator: DeqSimulator) -> bytes:
    simulator.send_frame(request_frame(0x00, build_sync_body()))
    return decode_frame(simulator.receive_frame(1.0)).body


def test_the_state_reaches_the_sync_reply():
    body = sync_reply_body(simulator_reading(
        DeqSimulatorState(volume_db=-5, muted=True, driving=True)))
    assert int.from_bytes(body[20:24], "little", signed=True) == -5
    assert int.from_bytes(body[24:28], "little") == 1
    assert int.from_bytes(body[28:32], "little") == 1


def test_a_volume_outside_the_units_range_is_held_at_the_limit():
    body = sync_reply_body(simulator_reading(DeqSimulatorState(volume_db=500)))
    assert int.from_bytes(body[20:24], "little", signed=True) == 10


def test_a_refused_open_answers_the_status_the_real_unit_answers():
    simulator = simulator_reading(DeqSimulatorState(refuses_sync=True))
    simulator.send_frame(request_frame(0x00, build_sync_body()))
    reply = decode_frame(simulator.receive_frame(1.0))
    assert reply.body == (-5).to_bytes(4, "little", signed=True)


def test_a_command_fault_answers_that_status():
    simulator = simulator_reading(
        DeqSimulatorState(status_by_command={"0x03": -7}))
    simulator.send_frame(request_frame(0x03))
    reply = decode_frame(simulator.receive_frame(1.0))
    assert reply.body == (-7).to_bytes(4, "little", signed=True)


def test_the_unit_can_be_told_to_go_quiet_after_a_command():
    simulator = simulator_reading(DeqSimulatorState(silent_after=[0x03]))
    simulator.send_frame(request_frame(0x03))
    assert decode_frame(simulator.receive_frame(1.0)).command_id == 0x03
    simulator.send_frame(request_frame(0x04))
    with pytest.raises(TransportTimeout):
        simulator.receive_frame(1.0)


def test_clearing_a_fault_makes_the_unit_answer_again():
    # The console clears a fault by writing a new state. A unit that stayed
    # mute afterwards would look like a hang rather than a cleared fault.
    state = DeqSimulatorState(silent_after=[0x03])
    simulator = DeqSimulator(load_state_function=lambda path: state)
    simulator.send_frame(request_frame(0x03))
    simulator.receive_frame(1.0)
    state.silent_after = []
    simulator.send_frame(request_frame(0x04))
    assert decode_frame(simulator.receive_frame(1.0)).command_id == 0x04


def test_the_state_is_re_read_for_every_frame():
    # A change in the console shows up in the next reply, with no restart.
    state = DeqSimulatorState(volume_db=-27)
    simulator = DeqSimulator(load_state_function=lambda path: state)
    assert int.from_bytes(sync_reply_body(simulator)[20:24], "little", signed=True) == -27
    state.volume_db = -3
    assert int.from_bytes(sync_reply_body(simulator)[20:24], "little", signed=True) == -3


def test_the_error_flags_reach_the_command_that_reports_them():
    simulator = simulator_reading(DeqSimulatorState(error_flags=0x81))
    simulator.send_frame(request_frame(0x17))
    body = decode_frame(simulator.receive_frame(1.0)).body
    assert int.from_bytes(body[4:8], "little") == 0x81
