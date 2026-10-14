"""Checks that a settings blob turns into the profile it holds."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.deq_blob import (
    BANK_BAND_SLOTS,
    STANDARD_BLOB_BYTES,
    CrossoverSetting,
    SpeakerRecord,
    UserConfiguration,
    decode_blob,
)
from app.deq_dsp import convert_wide_bands_to_equalizer_bands
from app.deq_protocol import decode_frame
from app.unit_tuning import tuning_from_configuration

REAL_REPLY_PATH = (
    Path(__file__).parent / "testing" / "captures"
    / "20261008_user_configuration_reply.hex"
)
STATUS_BYTES = 4


def load_real_configuration() -> UserConfiguration:
    """Returns the car's own blob, as its unit answered 0x09 on 2026-10-08."""
    reply = decode_frame(bytes.fromhex(REAL_REPLY_PATH.read_text().strip()))
    return decode_blob(reply.body[STATUS_BYTES:STATUS_BYTES + STANDARD_BLOB_BYTES])


def test_the_cars_own_tune_comes_through():
    tuning = tuning_from_configuration(load_real_configuration())

    assert tuning.speakers["FL"].levelDB == -2.0
    assert tuning.speakers["RR"].levelDB == 2.0
    assert tuning.speakers["FL"].timeAlignmentCm == 65.0
    assert tuning.filter.front.cutoff_hpf == 6
    assert tuning.filter.rear.cutoff_hpf == 8
    assert tuning.foundationEq.eqs["LR"].banks == [[0.0] * 13, [0.0] * 13]


def test_the_cars_factory_cancelling_comes_through():
    """The car's unit stores a cancelling curve for its factory speakers, and
    both flags are on."""
    configuration = load_real_configuration()

    cancel = tuning_from_configuration(configuration).factoryCancel

    assert cancel.available and cancel.enabled
    assert cancel.data.cancellingEQ.L == configuration.cancelling_left_db


def test_a_31_band_bank_becomes_the_13_bands_the_push_would_send():
    wide_gains_db = [float(band % 5) - 2 for band in range(BANK_BAND_SLOTS)]
    configuration = UserConfiguration(band_count=31, bank_a_gains_db=wide_gains_db)

    slot = tuning_from_configuration(configuration).foundationEq.eqs["LR"]

    assert slot.numOfBand == 13
    assert slot.banks[0] == convert_wide_bands_to_equalizer_bands(wide_gains_db)


def test_a_13_band_bank_keeps_its_first_13_slots():
    slot_gains_db = [float(band) for band in range(BANK_BAND_SLOTS)]
    configuration = UserConfiguration(band_count=13, bank_b_gains_db=slot_gains_db)

    slot = tuning_from_configuration(configuration).foundationEq.eqs["LR"]

    assert slot.banks[1] == slot_gains_db[:13]


def test_the_bank_in_use_becomes_the_selected_bank():
    configuration = UserConfiguration(bank_in_use=1)

    slot = tuning_from_configuration(configuration).foundationEq.eqs["LR"]

    assert slot.selectedBank == 1


def test_an_unknown_band_count_raises():
    with pytest.raises(ValueError, match="20-band"):
        tuning_from_configuration(UserConfiguration(band_count=20))


def test_each_cancelling_flag_lands_on_its_own_field():
    """Byte 370 is `enabled` and byte 371 is `available`, after the app's
    own writers."""
    only_available = UserConfiguration(cancelling_available=1)

    cancel = tuning_from_configuration(only_available).factoryCancel

    assert cancel.available and not cancel.enabled


def test_speaker_records_map_onto_the_four_profile_channels():
    speakers = [SpeakerRecord(level_db=float(record)) for record in range(7)]
    configuration = UserConfiguration(speakers=speakers)

    tuning = tuning_from_configuration(configuration)

    assert {channel: speaker.levelDB for channel, speaker in tuning.speakers.items()} == {
        "FL": 0.0, "FR": 1.0, "RL": 2.0, "RR": 3.0,
    }


def test_crossover_slots_0_and_1_become_the_front_and_rear_filter():
    crossovers = [CrossoverSetting(frequency=slot + 4, slope=slot) for slot in range(4)]

    tuning = tuning_from_configuration(UserConfiguration(crossovers=crossovers))

    assert (tuning.filter.front.cutoff_hpf, tuning.filter.front.slope_hpf) == (4, 0)
    assert (tuning.filter.rear.cutoff_hpf, tuning.filter.rear.slope_hpf) == (5, 1)
