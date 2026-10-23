"""Checks that the Pi gadget's frame encoder still matches this one.

`pi-gadget/deq_accessory.py` repeats `encode_frame`, because the Pi runs
that one file with no backend beside it. Two encoders for one wire format
drift apart, so this test encodes the same frames with both.

The gadget writes to configfs and opens the accessory device as soon as it
runs, so a test cannot import it. This test takes the few statements that
define the encoder and the values it reads, and runs only those.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.deq_protocol import Direction, Message, encode_frame

GADGET_PATH = Path(__file__).resolve().parents[2] / "pi-gadget" / "deq_accessory.py"

# A backend tree copied to the Pi has no `pi-gadget/` beside it. The
# repository always has one, so CI runs this test.
pytestmark = pytest.mark.skipif(
    not GADGET_PATH.exists(), reason="no pi-gadget/ beside this backend tree"
)

# The names the gadget's `build_frame` and its frame lists need.
GADGET_NAMES = {
    "DIRECTION_TO_DEVICE",
    "FRAME_START_MARKER",
    "FRAME_END_MARKER",
    "FRAME_HEADER",
    "PAYLOAD_HEADER_LENGTH",
    "LENGTH_FIELD_BIAS",
    "STARTUP_BURST",
    "SYNC_BODY",
    "SET_TIMEOUT_INTERVAL_BODY",
    "GET_OPAL_CONFIGURATION_BODY",
    "COLD_START_READS",
    "build_frame",
}

# Ids at both ends of the byte and past the wrap, which the gadget reaches
# in about fifty minutes of keepalives.
TRANSACTION_IDS = (1, 0x3A, 0xFF, 0x100)


def statement_names(statement: ast.stmt) -> list[str]:
    if isinstance(statement, ast.Assign):
        return [target.id for target in statement.targets if isinstance(target, ast.Name)]
    if isinstance(statement, ast.FunctionDef):
        return [statement.name]
    return []


def load_gadget_namespace() -> dict:
    """Returns the gadget's encoder and its frame lists, and nothing else."""
    module = ast.parse(GADGET_PATH.read_text())
    found = {
        name: statement
        for statement in module.body
        for name in statement_names(statement)
        if name in GADGET_NAMES
    }
    missing = sorted(GADGET_NAMES - set(found))
    assert missing == [], f"{GADGET_PATH.name} no longer defines {missing}"
    namespace: dict = {}
    selected = ast.Module(body=list(found.values()), type_ignores=[])
    exec(compile(ast.fix_missing_locations(selected), str(GADGET_PATH), "exec"), namespace)
    return namespace


def gadget_cases() -> list[tuple[int, bytes]]:
    """Returns every frame the gadget sends, and the edges a body can reach."""
    namespace = load_gadget_namespace()
    sent_frames = namespace["STARTUP_BURST"] + namespace["COLD_START_READS"]
    cases = [(command_id, body) for _gap, command_id, body in sent_frames]
    cases += [
        (0x00, namespace["SYNC_BODY"]),
        (0x02, b""),
        (0x05, bytes(range(256))),
        (0x0D, b"\xff" * 4),
    ]
    return cases


@pytest.mark.parametrize("transaction_id", TRANSACTION_IDS)
def test_the_gadget_encodes_every_frame_as_the_backend_does(transaction_id):
    build_frame = load_gadget_namespace()["build_frame"]
    for command_id, body in gadget_cases():
        from_backend = encode_frame(
            Message(
                direction=Direction.TO_DEVICE,
                command_id=command_id,
                transaction_id=transaction_id.to_bytes(8, "little"),
                body=body,
            )
        )
        assert build_frame(command_id, transaction_id, body) == from_backend, (
            f"command 0x{command_id:02x}, transaction id {transaction_id}"
        )
