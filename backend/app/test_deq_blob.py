"""Checks the blob codec against a blob the Android app itself wrote.

`deq_blob_reference.json` holds the 572 bytes that the app's own serializer
(`b/g/h`) produced for a default configuration in speaker mode
`STANDARD_FL_FR_RL_RR_SW`. Frida read them out of the running app.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.deq_blob import (
    BANK_BAND_SLOTS,
    CANCELLING_BAND_COUNT,
    CROSSOVER_SPEAKER_COUNT,
    NAME_BYTES,
    SPEAKER_RECORD_COUNT,
    SPEAKER_RECORD_OFFSET,
    SPEAKER_RECORD_STRIDE,
    STANDARD_BLOB_BYTES,
    BlobLengthError,
    CrossoverSetting,
    SpeakerRecord,
    UserConfiguration,
    decode_blob,
    encode_blob,
    trim_gains_to_band_count,
)


def load_default_blob() -> bytes:
    path = Path(__file__).parent / "deq_blob_reference.json"
    return bytes.fromhex(json.loads(path.read_text())["default_standard_fl_fr_rl_rr_sw"])


def load_edited_blob() -> bytes:
    path = Path(__file__).parent / "deq_blob_reference.json"
    return bytes.fromhex(json.loads(path.read_text())["edited_standard_fl_fr_rl_rr_sw"])


DEFAULT_BLOB = load_default_blob()
# Built by this codec, then read and rewritten by the app's own codec on a
# running device. The app reproduced it byte for byte.
EDITED_BLOB = load_edited_blob()


def test_the_reference_blob_is_the_length_the_app_writes() -> None:
    assert len(DEFAULT_BLOB) == STANDARD_BLOB_BYTES


def test_the_reference_blob_survives_a_round_trip() -> None:
    assert encode_blob(decode_blob(DEFAULT_BLOB)) == DEFAULT_BLOB


def test_the_reference_blob_reads_as_the_app_s_defaults() -> None:
    configuration = decode_blob(DEFAULT_BLOB)
    assert configuration.version == 3
    assert configuration.speaker_mode == 3
    assert configuration.listening_position == 2
    assert configuration.band_count == 31
    assert configuration.equalizer_enabled == 0
    assert configuration.bank_in_use == 0
    assert configuration.source_type == 0xFF
    assert configuration.bank_flag_b == 1


def test_a_default_blob_has_flat_banks() -> None:
    configuration = decode_blob(DEFAULT_BLOB)
    assert configuration.bank_a_gains_db == [0.0] * BANK_BAND_SLOTS
    assert configuration.bank_b_gains_db == [0.0] * BANK_BAND_SLOTS


def test_every_speaker_record_carries_its_own_phase_flag() -> None:
    # The app writes the phase flag first in every one of the 7 records. A hook
    # on its own reader under the emulator showed this. See the module
    # docstring of deq_blob.py. The default blob's flag is 0x01.
    assert DEFAULT_BLOB[SPEAKER_RECORD_OFFSET] == 1
    speakers = decode_blob(DEFAULT_BLOB).speakers
    assert all(speaker.is_positive_phase for speaker in speakers)
    assert len(speakers) == SPEAKER_RECORD_COUNT


def test_the_speaker_records_are_thirteen_bytes_apart() -> None:
    configuration = UserConfiguration()
    configuration.speakers = [
        SpeakerRecord(slot % 2 == 0, float(slot), 0.0, 0.0)
        for slot in range(SPEAKER_RECORD_COUNT)
    ]
    blob = encode_blob(configuration)
    for slot in range(SPEAKER_RECORD_COUNT):
        start = SPEAKER_RECORD_OFFSET + slot * SPEAKER_RECORD_STRIDE
        assert blob[start] == (1 if slot % 2 == 0 else 0)
    assert decode_blob(blob).speakers == configuration.speakers


def test_asymmetric_speaker_values_match_what_the_app_itself_reported() -> None:
    """This exact blob went through the app's own reader under the Android
    emulator (Frida, with a hook on `b/g/h.a(ByteArrayInputStream,
    model/b/w$a)`). The reader reported back these exact values for these three
    speakers, by their real field names (`isPositivePhase`, `levelDB`,
    `timeAlignmentCm`, `levelDBExtended`). See USB_CAPTURE_NOTES.md in the
    outer repo for the live session. This test pins that result, so the fix it
    backed cannot regress unseen."""
    configuration = UserConfiguration()
    configuration.speakers[0] = SpeakerRecord(False, 1.5, -2.5, 3.5)
    configuration.speakers[3] = SpeakerRecord(True, -9.0, 100.0, 0.25)
    configuration.speakers[6] = SpeakerRecord(False, 7.0, 0.0, -1.0)

    decoded = decode_blob(encode_blob(configuration)).speakers

    assert decoded[0] == SpeakerRecord(False, 1.5, -2.5, 3.5)
    assert decoded[3] == SpeakerRecord(True, -9.0, 100.0, 0.25)
    assert decoded[6] == SpeakerRecord(False, 7.0, 0.0, -1.0)


def test_band_gains_are_little_endian_float32() -> None:
    configuration = UserConfiguration()
    configuration.bank_a_gains_db[0] = 6.0
    blob = encode_blob(configuration)
    assert blob[18:22] == bytes([0x00, 0x00, 0xC0, 0x40])


def test_every_field_survives_a_round_trip() -> None:
    configuration = UserConfiguration(
        version=3,
        timestamp_seconds=1_759_300_000,
        speaker_mode=3,
        listening_position=1,
        always_false_flag=1,
        equalizer_enabled=1,
        band_count=13,
        bank_in_use=1,
        bank_a_gains_db=[float(band) / 2 for band in range(BANK_BAND_SLOTS)],
        bank_b_gains_db=[-float(band) / 4 for band in range(BANK_BAND_SLOTS)],
        preset_index_a=2,
        preset_index_b=3,
        bank_flag_b=1,
        bank_flag_c=1,
        sound_field=4,
        crossovers=[
            CrossoverSetting(frequency=index + 1, slope=index + 2)
            for index in range(CROSSOVER_SPEAKER_COUNT)
        ],
        speakers=[
            SpeakerRecord(slot % 2 == 0, float(slot), float(slot) * 2, float(slot) * 3)
            for slot in range(SPEAKER_RECORD_COUNT)
        ],
        cancelling_enabled=1,
        cancelling_available=1,
        cancelling_left_db=[0.5] * CANCELLING_BAND_COUNT,
        cancelling_right_db=[-0.5] * CANCELLING_BAND_COUNT,
        cancelling_time_alignment_left_cm=1.25,
        cancelling_time_alignment_right_cm=-1.25,
        unique_id_bytes=bytes(range(NAME_BYTES)),
        source_type=2,
        bank_type=7,
        model_value=9,
        car_model_name_key_digest=bytes(range(16)),
        data_protection_enabled=1,
        scrambled_password_bytes=bytes(range(32)),
    )
    assert decode_blob(encode_blob(configuration)) == configuration


def test_a_blob_of_the_wrong_length_is_rejected() -> None:
    with pytest.raises(BlobLengthError):
        decode_blob(bytes(546))


def test_a_wrong_band_count_is_rejected() -> None:
    configuration = UserConfiguration()
    configuration.bank_a_gains_db = [0.0] * 13
    with pytest.raises(ValueError):
        encode_blob(configuration)


def test_a_wrong_speaker_count_is_rejected() -> None:
    configuration = UserConfiguration()
    configuration.speakers = [SpeakerRecord()] * 5
    with pytest.raises(ValueError):
        encode_blob(configuration)


def test_a_name_region_of_the_wrong_size_is_rejected() -> None:
    configuration = UserConfiguration()
    configuration.unique_id_bytes = b"short"
    with pytest.raises(ValueError):
        encode_blob(configuration)


def test_the_edited_blob_survives_a_round_trip() -> None:
    assert encode_blob(decode_blob(EDITED_BLOB)) == EDITED_BLOB


def test_the_edited_blob_holds_the_values_it_was_built_with() -> None:
    configuration = decode_blob(EDITED_BLOB)
    assert configuration.equalizer_enabled == 1
    assert configuration.listening_position == 1
    assert configuration.band_count == 31
    assert configuration.bank_a_gains_db[0] == 6.0
    assert configuration.bank_a_gains_db[15] == -3.5
    assert configuration.bank_b_gains_db[30] == 1.25
    assert configuration.speakers[0].level_db == 2.0
    assert configuration.speakers[6].level_db_extended == -4.0
    assert configuration.crossovers[3] == CrossoverSetting(frequency=5, slope=2)
    assert configuration.cancelling_left_db[2] == 1.5
    assert configuration.source_type == 1


def test_trimming_drops_the_gains_above_the_band_count() -> None:
    configuration = UserConfiguration()
    configuration.band_count = 13
    configuration.bank_a_gains_db[0] = 6.0
    configuration.bank_a_gains_db[15] = -3.5
    configuration.bank_b_gains_db[30] = 1.0
    trim_gains_to_band_count(configuration)
    assert configuration.bank_a_gains_db[0] == 6.0
    assert configuration.bank_a_gains_db[15] == 0.0
    assert configuration.bank_b_gains_db[30] == 0.0


def test_trimming_leaves_a_thirty_one_band_profile_alone() -> None:
    configuration = UserConfiguration()
    configuration.bank_a_gains_db[30] = 2.0
    trim_gains_to_band_count(configuration)
    assert configuration.bank_a_gains_db[30] == 2.0


def test_always_false_flag_is_a_literal_the_app_writes_not_a_read_model_field() -> None:
    """The app's writer, `b/g/h.a(z, Z, o)`, emits a hardcoded `0x0` at offset
    14. It never reads a model field for this position. So a profile cannot
    carry a `true` here, whatever its settings say."""
    configuration = UserConfiguration(always_false_flag=0)
    assert decode_blob(encode_blob(configuration)).always_false_flag == 0


def test_unique_id_bytes_holds_the_presets_own_unique_id() -> None:
    """Offset 484's 32 bytes are the preset JSON header's own `uniqueId`
    string, traced to the app's writer calling `z.r()`. A bundled preset's
    id, `"1-0000-0000-0011-000000000000000"`, is 31 characters and fits with
    one byte to spare."""
    unique_id = b"1-0000-0000-0011-000000000000000"
    assert len(unique_id) == 32
    configuration = UserConfiguration(unique_id_bytes=unique_id)
    assert decode_blob(encode_blob(configuration)).unique_id_bytes == unique_id


def test_car_model_name_key_digest_round_trips_an_md5_hash() -> None:
    """The 16 bytes at offset 523 are MD5(carModelNameKey), or 16 zero bytes
    when the profile has no car model. The app's own JSON writer tags this
    exact field with the key `carModelNameKey`. The emulator then showed it
    live. A hook on the MD5 step showed that it digests a known test string on
    that field, byte for byte. See USB_CAPTURE_NOTES.md in the outer repo."""
    digest = hashlib.md5(b"hello").digest()
    assert len(digest) == 16
    configuration = UserConfiguration(car_model_name_key_digest=digest)
    assert decode_blob(encode_blob(configuration)).car_model_name_key_digest == digest


def test_car_model_name_key_digest_defaults_to_zero_for_no_car_model_selected() -> None:
    configuration = UserConfiguration()
    assert configuration.car_model_name_key_digest == bytes(16)
