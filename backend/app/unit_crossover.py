"""Maps the unit's stored crossover onto the five filter slots of command 0x05.

The settings blob stores one filter per speaker type, in this order: front,
rear, rear subwoofer and subwoofer (`CROSSOVER_SPEAKER_TYPES` in
`deq_blob.py`). The DSP addresses five filter slots instead. The speaker mode
decides which stored filter goes into which slot, and which slots stay on
Pass.

The Pioneer app holds the answer. `b/e/ab` switches on the speaker mode
(`ab$2`) and hands the stored filters to one of three builders in
`service/f`:

- `MakeSpeakerFilterStandardMode` takes the front filter for slot 0, the
  rear filter for slot 1 and the subwoofer's low pass for slot 4. It puts
  Pass in slots 2 and 3. A mode with no rear speakers passes no rear
  filter, and a mode with no subwoofer passes no subwoofer filter. Both
  then go out as Pass.
- `MakeSpeakerFilterStandardRearMode` takes the front filter for slot 0 and
  the rear subwoofer's low pass for slot 4.
- `MakeSpeakerFilterNetworkMode` serves the two NETWORK modes. This module
  does not map them, because `deq_blob.py` reads only the STANDARD form of
  the blob.

An earlier version copied stored filter n into slot n. In the car's mode
(STANDARD_FL_FR_RL_RR_SW) that put the subwoofer's low pass into slot 3,
which the standard layout never sends. So every push sent the subwoofer
unfiltered while the blob still named 50 Hz at 24 dB.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.deq_blob import CrossoverSetting as StoredFilter
from app.deq_dsp import CROSSOVER_SLOT_COUNT, SLOT_ROLES, FilterKind, FilterSlope
from app.deq_enums import SPEAKER_MODE

# The position of each speaker type in the blob's crossover list.
STORED_FRONT = 0
STORED_REAR = 1
STORED_REAR_SUBWOOFER = 2
STORED_SUBWOOFER = 3

# The names the Pioneer app gives the speaker types, in the blob's order.
STORED_FILTER_NAMES = ("front", "rear", "rear_subwoofer", "subwoofer")


@dataclass(frozen=True)
class CrossoverMap:
    """One speaker mode's crossover layout, and the stored filter in each slot."""

    layout: str
    stored_filter_by_slot: dict[int, int]


CROSSOVER_MAPS: dict[str, CrossoverMap] = {
    "STANDARD_FL_FR": CrossoverMap("standard", {0: STORED_FRONT}),
    "STANDARD_FL_FR_RL_RR": CrossoverMap(
        "standard", {0: STORED_FRONT, 1: STORED_REAR}
    ),
    "STANDARD_FL_FR_RL_RR_SW": CrossoverMap(
        "standard", {0: STORED_FRONT, 1: STORED_REAR, 4: STORED_SUBWOOFER}
    ),
    "STANDARD_FL_FR_RLSW_RRSW": CrossoverMap(
        "standard_rear", {0: STORED_FRONT, 4: STORED_REAR_SUBWOOFER}
    ),
    "STANDARD_FL_FR_SW": CrossoverMap(
        "standard", {0: STORED_FRONT, 4: STORED_SUBWOOFER}
    ),
}


class UnsupportedSpeakerModeError(ValueError):
    """Raised for a speaker mode whose crossover this module cannot map."""


def crossover_map(speaker_mode: int) -> CrossoverMap:
    """Returns the crossover map of one speaker mode, by its wire value."""
    name = SPEAKER_MODE.by_wire_value(speaker_mode).name
    if name not in CROSSOVER_MAPS:
        raise UnsupportedSpeakerModeError(
            f"speaker mode {name} has no crossover map"
        )
    return CROSSOVER_MAPS[name]


def crossover_slot_inputs(
    speaker_mode: int, stored_filters: list[StoredFilter]
) -> tuple[str, list[int], list[FilterSlope]]:
    """Returns the layout, and one cutoff position and slope per DSP slot.

    A slot that the mode does not fill stays on Pass.
    """
    mapping = crossover_map(speaker_mode)
    cutoff_positions = [0] * CROSSOVER_SLOT_COUNT
    slopes = [FilterSlope.PASS] * CROSSOVER_SLOT_COUNT
    for slot, stored_index in mapping.stored_filter_by_slot.items():
        stored = stored_filters[stored_index]
        cutoff_positions[slot] = stored.frequency
        slopes[slot] = FilterSlope(stored.slope)
    return mapping.layout, cutoff_positions, slopes


@dataclass(frozen=True)
class FilterRole:
    """What one stored filter does in one speaker mode."""

    stored_index: int
    slot: int
    kind: FilterKind
    uses_high_range: bool


def filter_roles(speaker_mode: int) -> list[FilterRole]:
    """Returns the stored filters that a speaker mode uses, in slot order.

    A Filter screen shows these and no others. The kind and the cutoff range
    come from `SLOT_ROLES`, which `conformance/flows.json` checks.
    """
    mapping = crossover_map(speaker_mode)
    roles = []
    for slot, stored_index in sorted(mapping.stored_filter_by_slot.items()):
        kind, uses_high_range = SLOT_ROLES[mapping.layout][slot]
        roles.append(FilterRole(stored_index, slot, kind, uses_high_range))
    return roles
