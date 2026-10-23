"""Checks the DSP maths against the app's own library.

`deq_dsp_reference.json` holds coefficients captured from
`jp.pioneer.mle.pmg.util.OpalParameter` on a running Sound & Tune app, with the
input that produced each one. The unit stores a coefficient as Q27. So two
designs that agree to one Q27 step produce the same bytes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.deq_dsp import (
    ATTENUATION_SILENT,
    CROSSOVER_CUTOFFS_HZ,
    LEVEL_BLOCK_BYTES,
    SPEAKER_LEVEL_OFF,
    SpeakerLevel,
    balance_bytes,
    build_level_payload,
    fader_bytes,
    speaker_level_byte,
    EQUALIZER_BAND_CENTRES_HZ,
    EQUALIZER_BAND_COUNT,
    Q27_UNITY,
    CrossoverSetting,
    FilterKind,
    FilterSlope,
    build_equalizer_block,
    build_equalizer_payload,
    build_time_alignment_block,
    build_time_alignment_payload,
    convert_wide_bands_to_equalizer_bands,
    decode_sections,
    design_crossover,
    crossover_cutoff_hz,
    design_equalizer_band,
    equalizer_band_push,
    fit_equalizer_gains,
    encode_sections,
    time_alignment_delays,
)

ONE_Q27_STEP = 1 / Q27_UNITY

CUTOFF_NAMES_HZ = {
    "FREQUENCY_25HZ": 25,
    "FREQUENCY_31_5HZ": 31.5,
    "FREQUENCY_40HZ": 40,
    "FREQUENCY_50HZ": 50,
    "FREQUENCY_63HZ": 63,
    "FREQUENCY_80HZ": 80,
    "FREQUENCY_100HZ": 100,
    "FREQUENCY_125HZ": 125,
    "FREQUENCY_160HZ": 160,
    "FREQUENCY_200HZ": 200,
    "FREQUENCY_250HZ": 250,
}

SLOPE_NAMES = {
    "SLOPE_6DB": FilterSlope.SLOPE_6,
    "SLOPE_12DB": FilterSlope.SLOPE_12,
    "SLOPE_18DB": FilterSlope.SLOPE_18,
    "SLOPE_24DB": FilterSlope.SLOPE_24,
}

SPEAKER_FILTER_KINDS = {
    "front": FilterKind.HIGH_PASS,
    "sub": FilterKind.LOW_PASS,
}


def load_reference() -> dict:
    path = Path(__file__).parent / "deq_dsp_reference.json"
    return json.loads(path.read_text())


REFERENCE = load_reference()


@pytest.mark.parametrize(
    "row",
    REFERENCE["equalizer"],
    ids=lambda row: f"band{row['band']}@{row['gain_db']:+g}dB",
)
def test_equalizer_band_matches_the_library(row: dict) -> None:
    designed = design_equalizer_band(
        EQUALIZER_BAND_CENTRES_HZ[row["band"]], row["gain_db"]
    )
    for ours, theirs in zip(designed, row["coefficients"]):
        assert abs(ours - theirs) <= ONE_Q27_STEP


@pytest.mark.parametrize(
    "row",
    [row for row in REFERENCE["crossover"]
     if row["cutoff"] in CUTOFF_NAMES_HZ],
    ids=lambda row: f"{row['speaker']}-{row['cutoff']}-{row['slope']}",
)
def test_crossover_pair_matches_the_library(row: dict) -> None:
    setting = CrossoverSetting(
        kind=SPEAKER_FILTER_KINDS[row["speaker"]],
        cutoff_hz=CUTOFF_NAMES_HZ[row["cutoff"]],
        slope=SLOPE_NAMES[row["slope"]],
    )
    first, second = design_crossover(setting)
    for ours, theirs in zip(first + second, row["coefficients"]):
        assert abs(ours - theirs) <= ONE_Q27_STEP


def test_a_flat_band_passes_the_signal_but_keeps_its_shape() -> None:
    forward_outer, forward_middle, forward_last, feedback_first, feedback_second = (
        design_equalizer_band(800, 0)
    )
    assert forward_outer == pytest.approx(1.0)
    # The numerator mirrors the denominator, so the section is a pass-through
    # without being the identity section a Pass crossover slot uses.
    assert forward_middle == pytest.approx(-feedback_first)
    assert forward_last == pytest.approx(-feedback_second)
    assert forward_middle != 0.0


def test_a_pass_crossover_slot_is_the_identity_section() -> None:
    first, second = design_crossover(
        CrossoverSetting(FilterKind.HIGH_PASS, 100, FilterSlope.PASS)
    )
    assert first == (1.0, 0.0, 0.0, 0.0, 0.0)
    assert second == first


def test_a_shallow_slope_leaves_the_second_slot_free() -> None:
    _, second = design_crossover(
        CrossoverSetting(FilterKind.LOW_PASS, 80, FilterSlope.SLOPE_12)
    )
    assert second == (1.0, 0.0, 0.0, 0.0, 0.0)


def test_an_equalizer_block_repeats_one_curve_over_four_channels() -> None:
    gains = [float(band) for band in range(EQUALIZER_BAND_COUNT)]
    block = build_equalizer_block(gains)
    assert len(block) == 52
    assert block[:13] == block[13:26] == block[26:39] == block[39:]


def test_an_equalizer_block_rejects_the_wrong_band_count() -> None:
    with pytest.raises(ValueError):
        build_equalizer_block([0.0] * 12)


@pytest.mark.parametrize("row", REFERENCE["band_conversion"])
def test_31_bands_become_13_exactly_as_the_library_does(row: dict) -> None:
    """These rows come from `ConvEq31to13` in `libPMGJni.so`, run under an
    emulator and rounded to float32 as the app keeps them. The equalizer
    truncates, so the match must be exact, not close."""
    assert convert_wide_bands_to_equalizer_bands(row["bands31"]) == row["bands13"]


def test_band_conversion_rejects_the_wrong_band_count() -> None:
    with pytest.raises(ValueError):
        convert_wide_bands_to_equalizer_bands([0.0] * EQUALIZER_BAND_COUNT)


def test_the_equalizer_payload_is_two_blocks_of_1040_bytes() -> None:
    flat = [0.0] * EQUALIZER_BAND_COUNT
    boosted = [6.0] + [0.0] * (EQUALIZER_BAND_COUNT - 1)
    payload = build_equalizer_payload(boosted, flat)
    assert len(payload) == 2080
    assert payload[:1040] != payload[1040:]


def test_coefficients_survive_a_round_trip_through_q27() -> None:
    sections = build_equalizer_block([3.0] * EQUALIZER_BAND_COUNT)
    for original, restored in zip(sections, decode_sections(encode_sections(sections))):
        for ours, theirs in zip(original, restored):
            assert abs(ours - theirs) <= ONE_Q27_STEP


def test_the_farthest_speaker_gets_no_delay() -> None:
    # Captured from the library: [100,200,300,400,500] -> [51,38,25,12,0].
    assert time_alignment_delays([100, 200, 300, 400, 500]) == [51, 38, 25, 12, 0]
    assert time_alignment_delays([7, 15, 23, 31, 39]) == [4, 3, 2, 1, 0]
    assert time_alignment_delays([500, 0, 0, 0, 0]) == [0, 64, 64, 64, 64]
    assert time_alignment_delays([1000] * 5) == [0] * 5


def test_the_time_alignment_block_is_eight_little_endian_words() -> None:
    payload = build_time_alignment_block([0, 0, 0, 0, 500])
    assert len(payload) == 16
    assert payload == bytes([64, 0, 64, 0, 64, 0, 64, 0, 0, 0, 0, 0, 0, 0, 0, 0])


def test_the_time_alignment_payload_sends_two_blocks() -> None:
    """The app calls `MakeTimeAlignment` twice and sends both results, so
    CONFIG_ID 10 declares 0x20 bytes, not 0x10."""
    cancelled = [0, 0, 0, 0, 500]
    plain = [0, 0, 0, 0, 1000]
    payload = build_time_alignment_payload(cancelled, plain)
    assert len(payload) == 32
    assert payload[:16] == build_time_alignment_block(cancelled)
    assert payload[16:] == build_time_alignment_block(plain)


def test_one_set_of_distances_fills_both_blocks() -> None:
    payload = build_time_alignment_payload([0, 0, 0, 0, 500])
    assert payload[:16] == payload[16:]


def test_time_alignment_rejects_the_wrong_speaker_count() -> None:
    with pytest.raises(ValueError):
        time_alignment_delays([0, 0, 0])


def test_the_cutoff_list_matches_the_eleven_positions_the_unit_offers() -> None:
    assert len(CROSSOVER_CUTOFFS_HZ) == 11
    assert CROSSOVER_CUTOFFS_HZ[0] == 25
    assert CROSSOVER_CUTOFFS_HZ[-1] == 250


def test_a_lone_band_keeps_its_own_gain() -> None:
    # Nothing pushes a band that has no same-sign neighbour, so the gain the
    # slider sends is the gain the library designs from.
    gains = [0.0] * EQUALIZER_BAND_COUNT
    gains[0] = 3.0
    assert fit_equalizer_gains(gains) == gains


def test_a_band_left_at_zero_stays_at_zero() -> None:
    # Two bands only interact when they share a sign, so a band at zero never
    # moves, however loud its neighbours are.
    gains = [6.0, 4.5, 3.0, 1.5] + [0.0] * (EQUALIZER_BAND_COUNT - 4)
    fitted = fit_equalizer_gains(gains)
    assert fitted[4:] == [0.0] * (EQUALIZER_BAND_COUNT - 4)


def test_two_bands_of_opposite_sign_do_not_interact() -> None:
    gains = [0.0] * EQUALIZER_BAND_COUNT
    gains[6], gains[7] = 6.0, -6.0
    assert fit_equalizer_gains(gains) == gains


def test_a_same_sign_neighbour_pulls_a_band_towards_zero() -> None:
    gains = [0.0] * EQUALIZER_BAND_COUNT
    gains[6], gains[7] = 6.0, 6.0
    fitted = fit_equalizer_gains(gains)
    assert fitted[6] == pytest.approx(5.8218)
    assert fitted[7] == pytest.approx(5.8218)


def test_a_band_at_one_db_or_less_pushes_nothing() -> None:
    assert equalizer_band_push(1.0) == 0.0
    assert equalizer_band_push(-0.5) == 0.0
    assert equalizer_band_push(1.5) != 0.0


def test_spreading_never_leaves_a_band_past_the_slider_range() -> None:
    # A band keeps a share of its own push. So a band at the top of the range,
    # with quiet same-sign neighbours, ends up above 12 dB before the clamp.
    # The library clamps there, and so does this code. Without the clamp, the
    # designed coefficient differs from the library's.
    gains = [12.0, 1.5, -6.0, 5.0, -12.0, -4.0, -4.5, -8.5, 8.5, 6.5, 12.0,
             -6.0, -2.0]
    fitted = fit_equalizer_gains(gains)
    assert max(fitted) == 12.0
    assert min(fitted) >= -12.0


def test_the_widest_spread_the_screen_offers_earns_453_samples() -> None:
    assert time_alignment_delays([3500, 0, 0, 0, 0])[1] == 453


def test_a_delay_counts_only_the_spread_not_the_distance() -> None:
    # The library works on the differences, so moving every speaker further
    # away changes nothing.
    assert (time_alignment_delays([3500, 3000, 2000, 1000, 500])
            == time_alignment_delays([3000, 2500, 1500, 500, 0]))


def test_a_spread_wider_than_the_screen_offers_is_an_error() -> None:
    # The library answers 100 and no coefficients. So this value is a bad
    # input, and not something to clamp without a word.
    with pytest.raises(ValueError):
        time_alignment_delays([3501, 0, 0, 0, 0])


def test_the_high_crossover_range_is_its_own_series() -> None:
    # The high range is not fifty times the low one. Nine positions happen to
    # match, but 31.5 Hz pairs with 1600 Hz and 125 Hz with 6300 Hz. Scaling by
    # fifty gives 1575 and 6250, which design a different filter than the app's.
    assert crossover_cutoff_hz(1, False) == 31.5
    assert crossover_cutoff_hz(1, True) == 1600
    assert crossover_cutoff_hz(7, False) == 125
    assert crossover_cutoff_hz(7, True) == 6300
    # the other nine do line up with fifty times the low value
    for position in (0, 2, 3, 4, 5, 6, 8, 9, 10):
        assert (crossover_cutoff_hz(position, True)
                == crossover_cutoff_hz(position, False) * 50)


# The level block the car's unit returned on 2026-10-08.
UNIT_LEVEL_BLOCK = bytes.fromhex(
    "160002f2" "fefe02020a00" "00fc" "0000" "000000000000" "10003e00ec000000"
)


@pytest.mark.parametrize(
    ("level_db", "expected"),
    [(0.0, 0), (-2.0, -2), (-1.5, -1), (2.7, 2), (-30.0, -24), (12.0, 10), (-128.0, SPEAKER_LEVEL_OFF)],
)
def test_a_speaker_level_is_clamped_and_truncated(level_db, expected):
    """`service/f.c(F)` clamps to -24..10 dB and truncates towards zero."""
    assert speaker_level_byte(level_db) == expected


@pytest.mark.parametrize(
    ("fader", "expected"),
    [(0, (0, 0)), (4, (0, -4)), (-4, (-4, 0)), (14, (0, -14)), (15, (0, ATTENUATION_SILENT)), (-20, (ATTENUATION_SILENT, 0))],
)
def test_a_fader_attenuates_one_side(fader, expected):
    assert fader_bytes(fader) == expected


def test_a_balance_attenuates_the_other_side_than_the_fader():
    """`service/f.b(I[B[B)` negates the value before it splits it."""
    assert balance_bytes(4) == (-4, 0)
    assert balance_bytes(-4) == (0, -4)


def test_the_unit_block_decodes_to_the_levels_the_blob_holds():
    """The car's fader of 4 gives the 00 fc that the unit returned."""
    assert fader_bytes(4) == (0, -4)
    unchanged = build_level_payload(
        UNIT_LEVEL_BLOCK,
        {
            "FL": SpeakerLevel(-2, 0),
            "FR": SpeakerLevel(-2, 0),
            "RL": SpeakerLevel(2, 0),
            "RR": SpeakerLevel(2, 0),
        },
        fader=4,
        balance=0,
    )
    assert unchanged == UNIT_LEVEL_BLOCK


def test_a_level_block_keeps_what_the_profile_does_not_name():
    """The source-mode levels, the subwoofer and the constants stay."""
    payload = build_level_payload(
        UNIT_LEVEL_BLOCK,
        {
            "FL": SpeakerLevel(-1.5, 0),
            "FR": SpeakerLevel(0, 0),
            "RL": SpeakerLevel(-4.5, 1),
            "RR": SpeakerLevel(-3.5, 0),
        },
        fader=0,
        balance=0,
    )
    assert len(payload) == LEVEL_BLOCK_BYTES
    assert payload == bytes.fromhex(
        "160002f2" "ff00fcfd0a00" "0000" "0000" "000001000000" "10003e00ec000000"
    )


def test_a_level_block_refuses_a_speaker_it_has_no_slot_for():
    with pytest.raises(ValueError, match="no slot"):
        build_level_payload(UNIT_LEVEL_BLOCK, {"C": SpeakerLevel(0, 0)}, fader=0, balance=0)


def test_a_level_block_refuses_a_unit_block_of_the_wrong_size():
    with pytest.raises(ValueError, match="28 bytes"):
        build_level_payload(UNIT_LEVEL_BLOCK[:20], {}, fader=0, balance=0)


# Level blocks that the app's own `b/e/ab` built in the emulator on
# 2026-10-23, from the car's source levels. `probe_level_block.js` in the
# outer repo's Frida scratch made them. Each case names all six slots, so
# the unit block plays no part in the speaker bytes.
APP_LEVEL_BLOCKS = [
    (
        "the car's own speakers",
        {"FL": (-2, 0), "FR": (-2, 0), "RL": (2, 0), "RR": (2, 0), "SW": (10, 0), "SW_REAR": (0, 0)},
        4,
        0,
        "160002f2fefe02020a0000fc000000000000000010003e00ec000000",
    ),
    (
        "the Duster profile",
        {"FL": (-1.5, 0), "FR": (0, 0), "RL": (-4.5, 1), "RR": (-3.5, 0), "SW": (0, 0), "SW_REAR": (0, 0)},
        0,
        0,
        "160002f2ff00fcfd00000000000000000100000010003e00ec000000",
    ),
    (
        "clamps, the off value and truncation",
        {"FL": (-30, -3), "FR": (12, 5), "RL": (-128, 0), "RR": (2.7, -1.9), "SW": (-9.9, 2), "SW_REAR": (4, 6)},
        -20,
        7,
        "160002f2e80a8002f7048000f900fd0500ff020610003e00ec000000",
    ),
    (
        "both sides silenced",
        {"FL": (0, 0), "FR": (0, 0), "RL": (0, 0), "RR": (0, 0), "SW": (0, 0), "SW_REAR": (0, 0)},
        15,
        -15,
        "160002f20000000000000080008000000000000010003e00ec000000",
    ),
]


@pytest.mark.parametrize(
    ("speakers", "fader", "balance", "expected_hex"),
    [case[1:] for case in APP_LEVEL_BLOCKS],
    ids=[case[0] for case in APP_LEVEL_BLOCKS],
)
def test_a_level_block_matches_the_apps_own_builder(speakers, fader, balance, expected_hex):
    payload = build_level_payload(
        UNIT_LEVEL_BLOCK,
        {name: SpeakerLevel(*levels) for name, levels in speakers.items()},
        fader=fader,
        balance=balance,
    )
    assert payload.hex() == expected_hex
