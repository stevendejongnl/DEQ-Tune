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
    CROSSOVER_CUTOFFS_HZ,
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
