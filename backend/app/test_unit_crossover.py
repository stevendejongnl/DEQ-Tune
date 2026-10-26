from __future__ import annotations

import pytest

from app.deq_blob import CrossoverSetting as StoredFilter
from app.deq_dsp import FilterKind, FilterSlope
from app.deq_enums import SPEAKER_MODE
from app.unit_crossover import (
    STORED_FILTER_NAMES,
    UnsupportedSpeakerModeError,
    crossover_slot_inputs,
    filter_roles,
)

# One distinct filter per stored entry, so a test can see which went where.
STORED = [
    StoredFilter(frequency=1, slope=1),
    StoredFilter(frequency=2, slope=2),
    StoredFilter(frequency=3, slope=3),
    StoredFilter(frequency=4, slope=4),
]


def mode(name: str) -> int:
    return SPEAKER_MODE.by_name(name).wire_value


@pytest.mark.parametrize(
    ("speaker_mode", "layout", "positions", "slopes"),
    [
        # `MakeSpeakerFilterStandardMode` with no rear and no subwoofer.
        ("STANDARD_FL_FR", "standard", [1, 0, 0, 0, 0], [1, 0, 0, 0, 0]),
        ("STANDARD_FL_FR_RL_RR", "standard", [1, 2, 0, 0, 0], [1, 2, 0, 0, 0]),
        # The car's mode: the subwoofer's low pass goes into slot 4.
        ("STANDARD_FL_FR_RL_RR_SW", "standard", [1, 2, 0, 0, 4], [1, 2, 0, 0, 4]),
        # `MakeSpeakerFilterStandardRearMode`: the rear subwoofer in slot 4.
        ("STANDARD_FL_FR_RLSW_RRSW", "standard_rear", [1, 0, 0, 0, 3], [1, 0, 0, 0, 3]),
        ("STANDARD_FL_FR_SW", "standard", [1, 0, 0, 0, 4], [1, 0, 0, 0, 4]),
    ],
)
def test_each_standard_mode_fills_the_slots_the_app_fills(
    speaker_mode: str, layout: str, positions: list[int], slopes: list[int]
) -> None:
    """The map follows `b/e/ab` and the three builders in `service/f`."""
    assert crossover_slot_inputs(mode(speaker_mode), STORED) == (
        layout,
        positions,
        [FilterSlope(slope) for slope in slopes],
    )


@pytest.mark.parametrize("speaker_mode", ["NETWORK_HL_HR_ML_MR", "NETWORK_HL_HR_ML_MR_SW"])
def test_a_network_mode_has_no_map(speaker_mode: str) -> None:
    with pytest.raises(UnsupportedSpeakerModeError):
        crossover_slot_inputs(mode(speaker_mode), STORED)


def test_the_cars_mode_shows_two_high_passes_and_the_subwoofer_low_pass() -> None:
    roles = filter_roles(mode("STANDARD_FL_FR_RL_RR_SW"))
    assert [
        (STORED_FILTER_NAMES[role.stored_index], role.kind, role.uses_high_range)
        for role in roles
    ] == [
        ("front", FilterKind.HIGH_PASS, False),
        ("rear", FilterKind.HIGH_PASS, False),
        ("subwoofer", FilterKind.LOW_PASS, False),
    ]


def test_the_rear_subwoofer_mode_shows_its_low_pass() -> None:
    roles = filter_roles(mode("STANDARD_FL_FR_RLSW_RRSW"))
    assert [STORED_FILTER_NAMES[role.stored_index] for role in roles] == [
        "front",
        "rear_subwoofer",
    ]
