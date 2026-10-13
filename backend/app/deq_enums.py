"""The DEQ's own value sets, read from the Pioneer app.

The Android app is the authority on every value the unit accepts. So these
values come from it, and this module chooses none. `tools/build_enums.py` reads
them out of the decompiled APK and writes `deq_enums.json`. This module loads
that file.

Two numbers per value, and they are not always the same. `ordinal` is the
constant's position in the Java enum. `wire_value` is what the protocol
carries, and it is the one to send. `BAND_13` is ordinal 0 but wire value 13.
Every `UNKNOWN` in a state enum is ordinal 0 but wire value -1.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ENUMS_PATH = Path(__file__).with_name("deq_enums.json")


@dataclass(frozen=True)
class EnumValue:
    """One constant of one DEQ value set."""

    name: str
    ordinal: int
    wire_value: int
    string_id: str | None


class DeqEnum:
    """One of the DEQ's value sets.

    It answers what the unit accepts for one field. You look a value up by name
    or by wire value. It depends on nothing but the generated JSON.
    """

    def __init__(self, enum_name: str, apk_class: str, values: list[EnumValue]) -> None:
        self.enum_name = enum_name
        self.apk_class = apk_class
        self.values = tuple(values)
        self._by_name = {value.name: value for value in values}
        self._by_wire_value = {value.wire_value: value for value in values}

    def __iter__(self):
        return iter(self.values)

    def __len__(self) -> int:
        return len(self.values)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(value.name for value in self.values)

    @property
    def selectable(self) -> tuple[EnumValue, ...]:
        """The values a person can choose, in wire order.

        A value with no `string_id` has no label in the app's own resources, so
        the real app never offers it. `UNKNOWN` is the case that matters. A
        decoder returns it for a wire value it does not recognise, and it is no
        setting. The app's own picker drops such a value. `p$f$a.a()` returns
        null for it, and the list builder skips the entry. So any code that
        offers a choice must read this property, and not `values`.
        """
        return tuple(value for value in self.values if value.string_id is not None)

    def by_name(self, name: str) -> EnumValue:
        """Looks one value up by its Java name, for example `SUPER_BASS`."""
        if name not in self._by_name:
            raise KeyError(f"{self.enum_name} has no value named {name!r}")
        return self._by_name[name]

    def by_wire_value(self, wire_value: int) -> EnumValue:
        """Looks one value up by the number the protocol carries."""
        if wire_value not in self._by_wire_value:
            raise KeyError(f"{self.enum_name} has no value with wire value {wire_value}")
        return self._by_wire_value[wire_value]


def _load_enums() -> dict[str, DeqEnum]:
    corpus = json.loads(ENUMS_PATH.read_text())
    enums = {}
    for enum_name, entry in corpus["enums"].items():
        values = [
            EnumValue(
                name=value["name"],
                ordinal=value["ordinal"],
                wire_value=value["wire_value"],
                string_id=value.get("string_id"),
            )
            for value in entry["values"]
        ]
        enums[enum_name] = DeqEnum(enum_name, entry["apk_class"], values)
    return enums


DEQ_ENUMS = _load_enums()

EQ_STYLE = DEQ_ENUMS["eq_style"]
LIVE_SIMULATION = DEQ_ENUMS["live_simulation"]
BAND_COUNT = DEQ_ENUMS["band_count"]
CUSTOM_BANK = DEQ_ENUMS["custom_bank"]
SPEAKER_MODE = DEQ_ENUMS["speaker_mode"]
CROSSOVER_SLOPE = DEQ_ENUMS["crossover_slope"]
CROSSOVER_KIND = DEQ_ENUMS["crossover_kind"]
DRIVING_STATE = DEQ_ENUMS["driving_state"]
MUTE_STATE = DEQ_ENUMS["mute_state"]
SPEAKER_CHANNEL = DEQ_ENUMS["speaker_channel"]
AUDIO_SOURCE = DEQ_ENUMS["audio_source"]
