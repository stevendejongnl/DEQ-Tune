"""Builds the DSP coefficients the Pioneer DEQ expects.

The DEQ does no filter design of its own. The Sound & Tune app computes every
coefficient and sends the finished numbers. To replace that app, this module
computes the same numbers.

The rules here come from measurement. The app ships its designer as
`libOpalParameterJNI.so` and calls it through
`jp.pioneer.mle.pmg.util.OpalParameter`. A Frida hook called that class with
known inputs, and the output of this module matches it to within one Q27 step.
`deq_dsp_reference.json` holds those captured input/output pairs.
`test_deq_dsp.py` checks every one of them.

The equalizer needs one step more than a filter design. The library spreads
every band's gain over the other bands before it designs a biquad. So a curve
with two raised bands is not two independent peakers. Its `fittingEqGain`
function does that step, from three constant tables. This module reproduces it
in `fit_equalizer_gains`, and matches the library's own output to 1e-14 dB over
every gain the sliders can send.

See `USB_CAPTURE_NOTES.md` in the outer repo for how the values came off the
unit and the library.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from enum import Enum

# The unit stores every coefficient as a signed 32-bit Q27 fixed-point value:
# 2 ** 27 means 1.0.
Q27_UNITY = 1 << 27

# The equalizer runs at 44100 Hz, the crossover at 48000 Hz. The two rates
# disagree, which looks wrong but is what the library does. Producing the same
# bytes the app produces matters more than picking one rate.
EQUALIZER_SAMPLE_RATE = 44100
CROSSOVER_SAMPLE_RATE = 48000

# Every equalizer band shares one Q and sits on a fixed centre frequency.
EQUALIZER_BAND_CENTRES_HZ = (
    50, 80, 125, 200, 315, 500, 800, 1250, 2000, 3150, 5000, 8000, 12500,
)
EQUALIZER_Q = 4.7

# One block holds four channels of the same curve.
EQUALIZER_CHANNELS_PER_BLOCK = 4
EQUALIZER_BAND_COUNT = len(EQUALIZER_BAND_CENTRES_HZ)

# A 31-band bank holds the ISO third-octave bands from 20 Hz to 20 kHz. The
# unit's own settings blob stores its tune in this form.
WIDE_BAND_COUNT = 31

# A crossover slot on Pass lets the signal through untouched.
IDENTITY_SECTION = (1.0, 0.0, 0.0, 0.0, 0.0)

# The cutoff list the app offers. The enum carries 22 names. The library folds
# them onto these 11 positions. The speaker's role decides whether a position
# means this frequency or fifty times it.
CROSSOVER_CUTOFFS_HZ = (
    25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250,
)
# The high range is its own 1/3-octave series, and not fifty times the low one.
# Nine of the eleven positions match fifty times the low value. But 31.5 Hz
# pairs with 1600 Hz and 125 Hz with 6300 Hz, not 1575 and 6250. The app's own
# enum names say so (FREQUENCY_1_6KHZ, FREQUENCY_6_3KHZ). The library agrees:
# those two cutoffs design a different filter.
CROSSOVER_HIGH_CUTOFFS_HZ = (
    1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500,
)


# A crossover payload is several blocks, concatenated in config-id order. Each
# block is a run of biquads. One block also carries a spare word.
CROSSOVER_BLOCK_BIQUADS = {3: 6, 4: 3, 5: 12}
CROSSOVER_BLOCK_SPARE_WORDS = {4: 1}

# Which blocks each speaker layout sends.
CROSSOVER_LAYOUT_BLOCKS = {
    "standard": (3, 4),
    "standard_rear": (3, 4),
    "network": (3, 4, 5),
}

# Which block and biquad each filter slot writes into. A slot owns that
# biquad and the next one: a shallow slope uses the first, a steeper one
# brings in the second. Slots absent from a layout are never written.
CROSSOVER_SLOT_POSITIONS = {
    "standard": {0: (3, 2), 1: (3, 4), 4: (4, 0)},
    "standard_rear": {0: (3, 2), 4: (4, 0)},
    "network": {0: (3, 2), 1: (3, 4), 2: (5, 6), 3: (5, 9), 4: (4, 0)},
}

CROSSOVER_SLOT_COUNT = 5

# Distances travel as millimetres and come back as sample delays. The library
# takes the speed of sound as 340 m/s, with no rounding.
SPEED_OF_SOUND_MM_PER_SECOND = 340_000
TIME_ALIGNMENT_SLOT_COUNT = 5
TIME_ALIGNMENT_BLOCK_WORDS = 8

# The screen stops at 350 cm between the nearest and the farthest speaker. That
# spread earns 453 samples. The library refuses a wider one and does not clamp
# it, so this module refuses it too. The library clamps the delay, and not the
# distance. Two layouts with the same spread give the same delays, however far
# away both speakers are.
TIME_ALIGNMENT_MAX_SPREAD_MM = 3500
TIME_ALIGNMENT_MAX_DELAY_SAMPLES = 453


# The library does not design each equalizer band straight from its slider. It
# first spreads every band's gain over its neighbours, then designs the biquads
# from the spread gains. `fit_equalizer_gains` below does that step. The three
# tables come from the library's own constant pool. The comments say what each
# one controls.

# How hard a band pushes, by its gain rounded up to whole dB. A band at
# 1 dB or less pushes nothing, so the table starts at 2 dB.
# Several entries are not the decimal they look like. They are the exact
# doubles the library holds, and the equalizer truncates towards zero, so a
# rounded constant here changes real bytes. Do not tidy them.
EQUALIZER_PUSH_WEIGHTS = (
    0.05,
    0.065,
    0.08,
    0.095,
    0.11,
    0.125,
    0.14,
    0.155,
    0.17,
    0.185,
    0.19999999999999998,
    0.215,
    0.23,
    0.245,
    0.26,
    0.275,
    0.29000000000000004,
    0.30500000000000005,
    0.31999999999999995,
    0.33499999999999996,
    0.35,
    0.365,
    0.38,
    0.395,
)

# How the push falls off with the distance between two bands, in band steps.
EQUALIZER_PUSH_DECAY = (
    1.0,
    0.47619047619047616,
    0.22675736961451246,
    0.1079796998164345,
    0.051418904674492616,
    0.02448519270213934,
    0.011659615572447303,
    0.005552197891641572,
    0.002643903757924558,
    0.0012590017894878848,
    0.0005995246616608976,
    0.0002854879341242369,
)

# How strongly each band reacts. The outer bands move more than the middle.
EQUALIZER_BAND_REACTION = (
    1.9, 1.3, 1.12, 1.05, 1.02,
    1.0, 1.0, 1.0, 1.02, 1.05,
    1.12, 1.3, 1.9,
)

# A band loses this share of its neighbour's push and keeps this share of
# its own.
EQUALIZER_PUSH_SHARE = 0.3
EQUALIZER_KEEP_SHARE = 0.03

# The sliders stop at 12 dB, and spreading the gains can carry a band past
# that. The library clamps before it designs, so this module clamps too.
EQUALIZER_GAIN_LIMIT_DB = 12.0


class FilterKind(str, Enum):
    HIGH_PASS = "high_pass"
    LOW_PASS = "low_pass"


class FilterSlope(int, Enum):
    """Crossover steepness in dB per octave. The value is the filter order."""

    PASS = 0
    SLOPE_6 = 1
    SLOPE_12 = 2
    SLOPE_18 = 3
    SLOPE_24 = 4


# The Q of each second-order section of a Butterworth of this order, in the
# order the library writes them. `None` marks a first-order section. Orders 5
# and 6 exist in the app's enum but crash the library, so they are absent here.
BUTTERWORTH_SECTION_QS: dict[FilterSlope, tuple[float | None, ...]] = {
    FilterSlope.SLOPE_6: (None,),
    FilterSlope.SLOPE_12: (0.7071067811865476,),
    FilterSlope.SLOPE_18: (1.0, None),
    FilterSlope.SLOPE_24: (1.3065629648763764, 0.5411961001461969),
}

# A biquad as the unit stores it: numerator, then the negated denominator.
Biquad = tuple[float, float, float, float, float]


@dataclass(frozen=True)
class CrossoverSetting:
    """One speaker's crossover, as the filter screen presents it."""

    kind: FilterKind
    cutoff_hz: float
    slope: FilterSlope


def crossover_cutoff_hz(position: int, uses_high_range: bool) -> float:
    """Returns the cutoff one position means, for a low or a high speaker."""
    table = (
        CROSSOVER_HIGH_CUTOFFS_HZ if uses_high_range else CROSSOVER_CUTOFFS_HZ
    )
    return float(table[position])


# The unit addresses five filter slots, whatever the layout drives. This table
# says which side of the crossover each slot is, and which cutoff range its
# position code means. Both came back out of the library's own output, and
# `conformance/flows.json` checks them byte for byte.
#
# A slot that a layout's table does not hold is a slot that layout does not
# drive.
SLOT_ROLES: dict[str, dict[int, tuple[FilterKind, bool]]] = {
    "standard": {
        0: (FilterKind.HIGH_PASS, False),
        1: (FilterKind.HIGH_PASS, False),
        4: (FilterKind.LOW_PASS, False),
    },
    "standard_rear": {
        0: (FilterKind.HIGH_PASS, False),
        4: (FilterKind.LOW_PASS, False),
    },
    "network": {
        0: (FilterKind.HIGH_PASS, True),
        1: (FilterKind.HIGH_PASS, False),
        2: (FilterKind.LOW_PASS, True),
        3: (FilterKind.LOW_PASS, True),
        4: (FilterKind.LOW_PASS, False),
    },
}

CROSSOVER_SLOT_COUNT = 5


def crossover_slot_settings(
    layout: str,
    cutoff_positions: list[int],
    slopes: list[FilterSlope],
) -> list[CrossoverSetting | None]:
    """Turns each slot's cutoff position and slope into a filter setting.

    A slot the layout does not drive, and a slot set to Pass, both give
    None, which `build_crossover_payload` leaves as an identity biquad.

    `cutoff_positions` holds a position in the 11-entry table, not a
    frequency. The same position means a low or a high cutoff depending on
    the slot's role, so the role picks the table.
    """
    if layout not in SLOT_ROLES:
        raise ValueError(f"unknown crossover layout {layout!r}")
    for name, values in (("cutoff positions", cutoff_positions), ("slopes", slopes)):
        if len(values) != CROSSOVER_SLOT_COUNT:
            raise ValueError(
                f"expected {CROSSOVER_SLOT_COUNT} {name}, got {len(values)}"
            )

    settings: list[CrossoverSetting | None] = []
    for slot in range(CROSSOVER_SLOT_COUNT):
        role = SLOT_ROLES[layout].get(slot)
        if role is None or slopes[slot] is FilterSlope.PASS:
            settings.append(None)
            continue
        kind, uses_high_range = role
        settings.append(
            CrossoverSetting(
                kind=kind,
                cutoff_hz=crossover_cutoff_hz(cutoff_positions[slot], uses_high_range),
                slope=slopes[slot],
            )
        )
    return settings


def equalizer_band_push(gain_db: float) -> float:
    """Returns how hard one band pushes the other bands.

    The library picks the weight by the gain rounded up to whole dB. A band at
    one dB or less pushes nothing.
    """
    weight_index = min(math.ceil(abs(gain_db)), len(EQUALIZER_PUSH_WEIGHTS)) - 2
    if weight_index < 0:
        return 0.0
    return EQUALIZER_PUSH_WEIGHTS[weight_index] * gain_db


def fit_equalizer_gains(band_gains_db: list[float]) -> list[float]:
    """Returns the gains the library designs its biquads from.

    A band that shares its sign with another band pulls that band towards zero.
    Two bands of opposite sign do not interact at all, so a band left at zero
    stays at zero. The spread can push a band past the slider range, so this
    function clamps the result to the range the sliders allow.
    """
    # The order of these multiplies and adds follows the library's own, step
    # for step. Collected terms give the same number in real arithmetic. In
    # float64 they give a different last bit. The equalizer truncates, so a
    # last bit can change a stored coefficient.
    fitted_gains_db = list(band_gains_db)
    for source in range(len(band_gains_db)):
        if band_gains_db[source] == 0:
            continue
        for target in range(len(band_gains_db)):
            if target == source or band_gains_db[target] == 0:
                continue
            if (band_gains_db[source] > 0) != (band_gains_db[target] > 0):
                continue
            spread = equalizer_band_push(band_gains_db[source])
            spread *= EQUALIZER_PUSH_DECAY[abs(source - target) - 1]
            spread *= EQUALIZER_BAND_REACTION[target]
            fitted_gains_db[target] -= EQUALIZER_PUSH_SHARE * spread
            fitted_gains_db[source] += EQUALIZER_KEEP_SHARE * spread
    return [
        max(-EQUALIZER_GAIN_LIMIT_DB, min(EQUALIZER_GAIN_LIMIT_DB, gain_db))
        for gain_db in fitted_gains_db
    ]


def design_equalizer_band(centre_hz: float, gain_db: float) -> Biquad:
    """Returns one equalizer section.

    The filter is an asymmetric constant-Q peaker. A boost widens the numerator
    and leaves the denominator alone. A cut widens the denominator and leaves
    the numerator alone. At 0 dB both branches give a section whose numerator
    mirrors its denominator. So the section passes the signal unchanged and
    keeps its centre and Q.
    """
    angular_frequency = 2 * math.pi * centre_hz / EQUALIZER_SAMPLE_RATE
    alpha = math.sin(angular_frequency) / (2 * EQUALIZER_Q)
    amplitude = 10 ** (gain_db / 20)

    if amplitude >= 1:
        numerator_alpha = alpha * amplitude
        denominator_alpha = alpha
    else:
        numerator_alpha = alpha
        denominator_alpha = alpha / amplitude

    scale = 1 + denominator_alpha
    feedback_first = -2 * math.cos(angular_frequency) / scale
    return (
        (1 + numerator_alpha) / scale,
        feedback_first,
        (1 - numerator_alpha) / scale,
        -feedback_first,
        -(1 - denominator_alpha) / scale,
    )


def convert_wide_bands_to_equalizer_bands(wide_gains_db: list[float]) -> list[float]:
    """Returns the 13 equalizer gains for one 31-band bank.

    The app does this with `ConvEq31to13` in `libPMGJni.so`, before it adds
    the cancelling equalizer. Each output band averages the third-octave
    bands around its own centre. The end bands take more neighbours.

    The sums follow the library's order, operand for operand. Another order
    changes the last bit, and the equalizer truncates. The library works in
    float64 and the app keeps the gains as float32, so this function rounds
    each input and each result to float32 too.
    """
    if len(wide_gains_db) != WIDE_BAND_COUNT:
        raise ValueError(
            f"expected {WIDE_BAND_COUNT} band gains, got {len(wide_gains_db)}"
        )
    gains = [_to_float32(gain_db) for gain_db in wide_gains_db]
    lowest = (gains[0] + gains[1] + gains[2] + gains[3] + gains[4] * 5 + gains[5]) / 10
    middle = [
        (
            (gains[2 * band + 3] + (gains[2 * band + 4] + gains[2 * band + 4]))
            + gains[2 * band + 5]
        )
        * 0.25
        for band in range(1, EQUALIZER_BAND_COUNT - 1)
    ]
    highest = (gains[27] + gains[28] * 3 + gains[29] + gains[30]) / 6
    return [_to_float32(gain_db) for gain_db in [lowest, *middle, highest]]


def _to_float32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def build_equalizer_block(band_gains_db: list[float]) -> list[Biquad]:
    """Returns one 52-section equalizer block: four channels of 13 bands.

    The app writes the same curve into all four channels. Which physical
    output each channel drives is not known and does not change the bytes.
    """
    if len(band_gains_db) != EQUALIZER_BAND_COUNT:
        raise ValueError(
            f"expected {EQUALIZER_BAND_COUNT} band gains, got {len(band_gains_db)}"
        )
    fitted_gains_db = fit_equalizer_gains(band_gains_db)
    one_channel = [
        design_equalizer_band(centre_hz, gain_db)
        for centre_hz, gain_db in zip(EQUALIZER_BAND_CENTRES_HZ, fitted_gains_db)
    ]
    return one_channel * EQUALIZER_CHANNELS_PER_BLOCK


def build_equalizer_payload(
    cancelled_band_gains_db: list[float],
    plain_band_gains_db: list[float],
) -> bytes:
    """Returns the body of command 0x05 CONFIG_ID 13.

    The unit wants two blocks: the curve with the cancelling equalizer applied,
    then the same curve without it.
    """
    sections = (
        build_equalizer_block(cancelled_band_gains_db)
        + build_equalizer_block(plain_band_gains_db)
    )
    return encode_sections(sections, Rounding.TRUNCATE)


def _design_first_order(kind: FilterKind, cutoff_hz: float) -> Biquad:
    warped = math.tan(math.pi * cutoff_hz / CROSSOVER_SAMPLE_RATE)
    pole = (1 - warped) / (1 + warped)
    if kind is FilterKind.HIGH_PASS:
        gain = 1 / (1 + warped)
        return (gain, -gain, 0.0, pole, 0.0)
    gain = warped / (1 + warped)
    return (gain, gain, 0.0, pole, 0.0)


def _design_second_order(kind: FilterKind, cutoff_hz: float, quality: float) -> Biquad:
    angular_frequency = 2 * math.pi * cutoff_hz / CROSSOVER_SAMPLE_RATE
    cosine = math.cos(angular_frequency)
    alpha = math.sin(angular_frequency) / (2 * quality)
    scale = 1 + alpha
    feedback_first = -2 * cosine / scale
    feedback_second = (1 - alpha) / scale
    if kind is FilterKind.HIGH_PASS:
        forward_outer = (1 + cosine) / 2 / scale
        forward_middle = -(1 + cosine) / scale
    else:
        forward_outer = (1 - cosine) / 2 / scale
        forward_middle = (1 - cosine) / scale
    return (
        forward_outer,
        forward_middle,
        forward_outer,
        -feedback_first,
        -feedback_second,
    )


def design_crossover(setting: CrossoverSetting) -> tuple[Biquad, Biquad]:
    """Returns the two sections one speaker's crossover occupies.

    The slope is the Butterworth order. An order that needs only one section
    leaves the second one as a pass-through.
    """
    if setting.slope is FilterSlope.PASS:
        return (IDENTITY_SECTION, IDENTITY_SECTION)

    sections = [
        _design_first_order(setting.kind, setting.cutoff_hz)
        if quality is None
        else _design_second_order(setting.kind, setting.cutoff_hz, quality)
        for quality in BUTTERWORTH_SECTION_QS[setting.slope]
    ]
    while len(sections) < 2:
        sections.append(IDENTITY_SECTION)
    return (sections[0], sections[1])


def build_crossover_payload(
    layout: str, settings: list[CrossoverSetting | None]
) -> bytes:
    """Returns the body of the crossover command for one speaker layout.

    `settings` holds one entry per filter slot, or None for a slot the layout
    does not use. A slot set to Pass leaves its two biquads as identity.
    """
    if layout not in CROSSOVER_LAYOUT_BLOCKS:
        raise ValueError(f"unknown speaker layout {layout!r}")
    if len(settings) != CROSSOVER_SLOT_COUNT:
        raise ValueError(
            f"expected {CROSSOVER_SLOT_COUNT} slots, got {len(settings)}"
        )

    blocks = {
        block_id: [list(IDENTITY_SECTION) for _ in range(CROSSOVER_BLOCK_BIQUADS[block_id])]
        for block_id in CROSSOVER_LAYOUT_BLOCKS[layout]
    }
    positions = CROSSOVER_SLOT_POSITIONS[layout]
    for slot, setting in enumerate(settings):
        if setting is None:
            continue
        if slot not in positions:
            raise ValueError(f"layout {layout!r} has no slot {slot}")
        block_id, first_biquad = positions[slot]
        first, second = design_crossover(setting)
        blocks[block_id][first_biquad] = list(first)
        blocks[block_id][first_biquad + 1] = list(second)

    payload = bytearray()
    for block_id in CROSSOVER_LAYOUT_BLOCKS[layout]:
        payload += encode_sections(
            [tuple(section) for section in blocks[block_id]], Rounding.NEAREST
        )
        payload += bytes(4 * CROSSOVER_BLOCK_SPARE_WORDS.get(block_id, 0))
    return bytes(payload)


def time_alignment_delays(distances_mm: list[int]) -> list[int]:
    """Returns one delay in samples per speaker.

    The farthest speaker gets no delay. Every nearer speaker waits for it. The
    library subtracts the distances first and scales afterwards, and truncates
    and does not round. It stops at the delay that the screen's longest
    distance earns. A wider spread than the screen offers is an error, and this
    function does not clamp it. The library refuses it, so this function
    raises.
    """
    if len(distances_mm) != TIME_ALIGNMENT_SLOT_COUNT:
        raise ValueError(
            f"expected {TIME_ALIGNMENT_SLOT_COUNT} distances, got {len(distances_mm)}"
        )
    spread_mm = max(distances_mm) - min(distances_mm)
    if spread_mm > TIME_ALIGNMENT_MAX_SPREAD_MM:
        raise ValueError(
            f"the nearest and the farthest speaker are {spread_mm} mm apart; "
            f"the unit accepts at most {TIME_ALIGNMENT_MAX_SPREAD_MM} mm"
        )
    farthest = max(distances_mm)
    return [
        min(
            (farthest - distance_mm) * EQUALIZER_SAMPLE_RATE
            // SPEED_OF_SOUND_MM_PER_SECOND,
            TIME_ALIGNMENT_MAX_DELAY_SAMPLES,
        )
        for distance_mm in distances_mm
    ]


def build_time_alignment_block(distances_mm: list[int]) -> bytes:
    """Returns one 16-byte time-alignment block: eight uint16, five used."""
    words = time_alignment_delays(distances_mm)
    words += [0] * (TIME_ALIGNMENT_BLOCK_WORDS - len(words))
    return b"".join(word.to_bytes(2, "little") for word in words)


def build_time_alignment_payload(
    cancelled_distances_mm: list[int],
    plain_distances_mm: list[int] | None = None,
) -> bytes:
    """Returns the body of command 0x05 CONFIG_ID 10: two blocks, 32 bytes.

    The app calls the library's `MakeTimeAlignment` twice and sends both
    results in one payload, the first argument's block first. Its CONFIG_ID
    10 field enum declares 0x20 bytes, which is these two blocks together.

    Pass one set of distances to send it as both blocks, which is what a
    profile with no cancelling data does.
    """
    if plain_distances_mm is None:
        plain_distances_mm = cancelled_distances_mm
    return build_time_alignment_block(cancelled_distances_mm) + build_time_alignment_block(
        plain_distances_mm
    )


# The level block, command 0x05 CONFIG_ID 0. `b/e/ab` builds it in Java, not in
# the library. It is 28 bytes, one signed byte per value:
#
#   0..3    a level per source mode: Car, SP, MIX, SP OTHER
#   4..9    a level per speaker slot, in LEVEL_SPEAKER_SLOTS order
#   10..11  the fader, as a front and a rear attenuation
#   12..13  the balance, as a left and a right attenuation
#   14..19  an extended level per speaker slot
#   20..27  constants: uint16 16, uint16 62, -20, three zeros
#
# A real unit answered `0x06` CONFIG_ID 0 with exactly this layout on
# 2026-10-08. Its front speakers read -2 dB, its rear +2 dB and its
# subwoofer +10 dB, which the settings blob also holds.
LEVEL_BLOCK_BYTES = 28
LEVEL_SPEAKER_OFFSET = 4
LEVEL_FADER_OFFSET = 10
LEVEL_BALANCE_OFFSET = 12
LEVEL_EXTENDED_OFFSET = 14

# The speaker slots of the level block. `ab$2` maps the app's speaker enum onto
# them: FRONT and HIGH share a slot, REAR and MID share a slot. "SW" is the
# subwoofer, and "SW_REAR" the app's REAR_R_SW. A profile names only the
# first four.
LEVEL_SPEAKER_SLOTS = ("FL", "FR", "RL", "RR", "SW", "SW_REAR")

# `service/f.c(F)` keeps a speaker level between these two values. It keeps
# -128 as it is, because -128 switches the speaker off.
SPEAKER_LEVEL_OFF = -128
SPEAKER_LEVEL_MIN_DB = -24
SPEAKER_LEVEL_MAX_DB = 10

# `service/f.a(I[B[B)` keeps a fader or a balance step between -15 and 15. An
# attenuation of 15 steps or more becomes -128, which silences that side.
ATTENUATION_LIMIT_STEPS = 15
ATTENUATION_SILENT = -128


def _to_signed_byte(value: int) -> int:
    """Wraps an integer the way Java's `int-to-byte` does."""
    return (value + 128) % 256 - 128


def speaker_level_byte(level_db: float) -> int:
    """Returns one speaker level as the level block holds it.

    The app clamps the level and then truncates it towards zero. So a profile
    level of -1.5 dB reaches the unit as -1 dB.
    """
    if level_db == SPEAKER_LEVEL_OFF:
        return SPEAKER_LEVEL_OFF
    clamped = min(max(level_db, SPEAKER_LEVEL_MIN_DB), SPEAKER_LEVEL_MAX_DB)
    return int(clamped)


def attenuation_pair(steps: int) -> tuple[int, int]:
    """Returns the two attenuations one fader value gives.

    A positive value attenuates the second side, and a negative value
    attenuates the first side. The other side stays at 0.
    """
    clamped = min(max(steps, -ATTENUATION_LIMIT_STEPS), ATTENUATION_LIMIT_STEPS)
    first, second = (0, -clamped) if clamped > 0 else (clamped, 0)
    return tuple(
        ATTENUATION_SILENT if side <= -ATTENUATION_LIMIT_STEPS else side
        for side in (first, second)
    )


def fader_bytes(fader: int) -> tuple[int, int]:
    """Returns the front and the rear attenuation of a fader value."""
    return attenuation_pair(fader)


def balance_bytes(balance: int) -> tuple[int, int]:
    """Returns the left and the right attenuation of a balance value.

    `service/f.b(I[B[B)` negates the value first. Then it does what the fader
    does.
    """
    return attenuation_pair(-balance)


@dataclass(frozen=True)
class SpeakerLevel:
    """One speaker's level and extended level, in dB."""

    level_db: float
    extended_db: float


def build_level_payload(
    unit_block: bytes,
    speaker_levels: dict[str, SpeakerLevel],
    fader: int,
    balance: int,
) -> bytes:
    """Returns the body of command 0x05 CONFIG_ID 0.

    `unit_block` is the block the unit holds now. The new block keeps each
    value that the arguments do not name: the source-mode levels, the
    constants, and every speaker slot that `speaker_levels` leaves out. The
    app does the same. It reads the source-mode levels from the unit, and it
    sends only the speakers of the profile in hand.
    """
    if len(unit_block) != LEVEL_BLOCK_BYTES:
        raise ValueError(
            f"a level block holds {LEVEL_BLOCK_BYTES} bytes, not {len(unit_block)}"
        )
    unknown_slots = set(speaker_levels) - set(LEVEL_SPEAKER_SLOTS)
    if unknown_slots:
        raise ValueError(f"the level block has no slot for {sorted(unknown_slots)}")
    values = list(struct.unpack(f"<{LEVEL_BLOCK_BYTES}b", unit_block))
    for slot, name in enumerate(LEVEL_SPEAKER_SLOTS):
        if name not in speaker_levels:
            continue
        speaker = speaker_levels[name]
        values[LEVEL_SPEAKER_OFFSET + slot] = speaker_level_byte(speaker.level_db)
        values[LEVEL_EXTENDED_OFFSET + slot] = _to_signed_byte(int(speaker.extended_db))
    values[LEVEL_FADER_OFFSET:LEVEL_FADER_OFFSET + 2] = fader_bytes(fader)
    values[LEVEL_BALANCE_OFFSET:LEVEL_BALANCE_OFFSET + 2] = balance_bytes(balance)
    return struct.pack(f"<{LEVEL_BLOCK_BYTES}b", *values)


class Rounding(str, Enum):
    """How a coefficient reaches its stored integer.

    The library does not pick one rule. Its equalizer builder truncates towards
    zero and its crossover builder rounds to nearest. The two disagree on about
    two coefficients in five. Each builder below passes the rule its own
    payload needs. The wrong rule changes the bytes.
    """

    TRUNCATE = "truncate"
    NEAREST = "nearest"


def to_q27(value: float, rounding: Rounding = Rounding.NEAREST) -> int:
    """Returns one coefficient as the unit stores it."""
    if rounding is Rounding.TRUNCATE:
        return int(value * Q27_UNITY)
    return round(value * Q27_UNITY)


def encode_sections(
    sections: list[Biquad], rounding: Rounding = Rounding.NEAREST
) -> bytes:
    """Returns biquad sections as little-endian Q27, five words per section."""
    return b"".join(
        to_q27(coefficient, rounding).to_bytes(4, "little", signed=True)
        for section in sections
        for coefficient in section
    )


def decode_sections(payload: bytes) -> list[Biquad]:
    """Returns the biquad sections a coefficient payload carries."""
    if len(payload) % 20:
        raise ValueError(f"payload of {len(payload)} bytes is not whole sections")
    words = [
        int.from_bytes(payload[offset:offset + 4], "little", signed=True) / Q27_UNITY
        for offset in range(0, len(payload), 4)
    ]
    return [tuple(words[start:start + 5]) for start in range(0, len(words), 5)]
