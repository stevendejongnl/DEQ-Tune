"""Checks the generated enums against what the APK says.

These values come from the Pioneer app. So a test here guards the copy, and not
a design choice. A person read every expected value below from the smali by
hand, and `USB_CAPTURE_NOTES.md` quotes each one.
"""

from __future__ import annotations

import pytest

from app.deq_enums import (
    AUDIO_SOURCE,
    BAND_COUNT,
    CROSSOVER_KIND,
    CROSSOVER_SLOPE,
    DEQ_ENUMS,
    DRIVING_STATE,
    EQ_STYLE,
    LIVE_SIMULATION,
    MUTE_STATE,
    SPEAKER_CHANNEL,
    SPEAKER_MODE,
)


def test_eq_style_carries_all_twenty_one_values():
    assert EQ_STYLE.names == (
        "UNKNOWN",
        "CUSTOM",
        "FLAT",
        "SUPER_BASS",
        "POWERFUL",
        "NATURAL",
        "VOCAL",
        "TODOROKI",
        "POP_ROCK",
        "ELETRONICA",
        "SAMBA",
        "SERTANEJO",
        "PRO",
        "BANDA",
        "DYNAMIC",
        "FORRO",
        "VIVID",
        "JAZZ",
        "ULTRA_BASS",
        "TRUE_ACOUSTIC",
        "EDM_BEAST",
    )


def test_live_simulation_carries_the_two_modes_the_app_ui_omitted():
    assert LIVE_SIMULATION.names == (
        "UNKNOWN",
        "OFF",
        "CONCERT_HALL",
        "OPEN_AIR",
        "CLUB",
        "CAFE",
        "OPERA_HALL",
        "DJ_DANCE_PARTY",
    )


def test_band_count_sends_the_band_number_not_the_ordinal():
    """`BAND_13` is ordinal 0 but sends 13. Sending the ordinal would
    select the wrong band layout."""
    assert BAND_COUNT.by_name("BAND_13").ordinal == 0
    assert BAND_COUNT.by_name("BAND_13").wire_value == 13
    assert BAND_COUNT.by_name("BAND_31").wire_value == 31


@pytest.mark.parametrize("deq_enum", [DRIVING_STATE, MUTE_STATE, CROSSOVER_KIND])
def test_unknown_sends_minus_one(deq_enum):
    assert deq_enum.by_name("UNKNOWN").wire_value == -1


def test_crossover_kind_shifts_down_by_one():
    assert CROSSOVER_KIND.by_name("HPF").wire_value == 0
    assert CROSSOVER_KIND.by_name("BPF").wire_value == 1
    assert CROSSOVER_KIND.by_name("LPF").wire_value == 2


def test_driving_state_matches_the_smali():
    assert DRIVING_STATE.by_name("RUNNING").wire_value == 0
    assert DRIVING_STATE.by_name("NOT_RUNNING").wire_value == 1


def test_mute_state_keeps_its_ordinals_apart_from_unknown():
    assert MUTE_STATE.by_name("SOUND_ON").wire_value == 1
    assert MUTE_STATE.by_name("SOUND_OFF").wire_value == 2


def test_crossover_slope_stops_at_thirty_six_decibels():
    assert CROSSOVER_SLOPE.names[0] == "SLOPE_PASS"
    assert CROSSOVER_SLOPE.names[-1] == "SLOPE_36DB"
    assert len(CROSSOVER_SLOPE) == 7


def test_speaker_mode_names_both_families():
    assert SPEAKER_MODE.by_name("STANDARD_FL_FR_RL_RR_SW").wire_value == 3
    assert SPEAKER_MODE.by_name("NETWORK_HL_HR_ML_MR_SW").wire_value == 7


def test_speaker_channel_covers_every_output():
    assert len(SPEAKER_CHANNEL) == 11
    assert SPEAKER_CHANNEL.names[0] == "FRONT_L"
    assert SPEAKER_CHANNEL.names[-1] == "SW"


def test_audio_source_names_the_connect_sequences_mode_command():
    """`0x0b`/MODE sends one of these. CAR_SOURCE and THROUGH both appear in
    the real (non-debug) state machine of `service/g.smali`, and not only on
    the "playground" screen. A trace of what `0x0b` meant showed this."""
    assert AUDIO_SOURCE.by_name("UNKNOWN").wire_value == -1
    assert AUDIO_SOURCE.by_name("CAR_SOURCE").wire_value == 3
    assert AUDIO_SOURCE.by_name("THROUGH").wire_value == 4
    assert len(AUDIO_SOURCE) == 10


def test_eq_style_keeps_the_app_storage_ids():
    assert EQ_STYLE.by_name("SUPER_BASS").string_id == "jp.pioneer.mle.soundtune.eq.superbass"
    assert EQ_STYLE.by_name("UNKNOWN").string_id is None


def test_wire_values_are_unique_within_each_enum():
    for enum_name, deq_enum in DEQ_ENUMS.items():
        wire_values = [value.wire_value for value in deq_enum]
        assert len(wire_values) == len(set(wire_values)), enum_name


def test_lookup_by_wire_value_round_trips():
    for deq_enum in DEQ_ENUMS.values():
        for value in deq_enum:
            assert deq_enum.by_wire_value(value.wire_value) is value


def test_an_unknown_name_raises():
    with pytest.raises(KeyError):
        EQ_STYLE.by_name("NOT_A_STYLE")
