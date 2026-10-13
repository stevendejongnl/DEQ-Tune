"""Reads and writes the DEQ's USER_CONFIGURATION blob.

The blob is the unit's whole semantic state. It holds which speakers the unit
drives, the band gains of both equalizer banks, the crossover settings, and the
per-speaker levels and delays. Command 0x09 reads it and command 0x08 writes it
back.

The DSP acts on the coefficients in command 0x05, so a profile has to send
both. See `deq_dsp.py` for the coefficient side.

The layout map came from one setting change at a time in the Android app. A
diff compared the bytes the app wrote after each change, from a single
baseline: speaker mode `STANDARD_FL_FR_RL_RR_SW`, blob version 3, 572 bytes. A
NETWORK mode writes two speaker records fewer, so it runs 26 bytes shorter.
This module reads and writes the STANDARD form only.

An earlier version of this module held four fields as unknown bytes. They now
have names. The app's own writer (`b/g/h.a(z, Z, o)[B` in the decompiled APK)
gave three of them. The fourth needed the app's own reader, run live under an
Android emulator with Frida, because a static read alone did not settle it. See
`USB_CAPTURE_NOTES.md` in the outer repo for both traces:

- Offset 14 is a literal `false` that the app always writes. It reads no
  model field at all.
- The 32 bytes at offset 484 are `uniqueId`, the same string that the
  preset JSON header carries (`"uniqueId": "1-0000-..."`). A default blob
  holds zeros there because the app's own default state has no id. The field itself has a known meaning.
- The 16 bytes at offset 523 are `MD5(carModelNameKey)`, or 16 zero bytes
  when the profile has no car model (`carModelNameKey` empty).
  `carModelNameKey` is the same string that the preset JSON header's own
  `carModelStringsKey` carries (`Header` in `eq_data.py`). The app's JSON
  writer tags its source field with that exact key, which gave the match.
  The emulator then showed it live. A hook on the MD5 step showed that it
  digests the string of a known test value, byte for byte.
- Offset 279 is no standalone flag between the crossover block and the
  speaker records. It is byte 0 of the phase flag of speaker record 0. A
  hook on the app's real per-speaker reader
  (`b/g/h.a(ByteArrayInputStream, model/b/w$a)`) logged the stream
  position before and after each of its 7 calls. Every record reads one
  phase-flag byte, then three float32. This module read three floats
  and then a trailing byte before. The two errors mostly cancelled, and
  the floats still landed on the right bytes. So every existing
  round-trip test passed. The error was in which speaker each phase
  flag belongs to.

**A bank always reserves 31 slots, but the unit reads only `band_count`
of them.** Set `band_count` to 13 and the app drops all values in slots 13
to 30. A gain above the band count does not survive the unit's next
write. `trim_gains_to_band_count` does that trim here, so a caller can
see it happen and does not lose the value later.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

BLOB_VERSION = 3
STANDARD_BLOB_BYTES = 572

VERSION_OFFSET = 0
TIMESTAMP_OFFSET = 4
SPEAKER_MODE_OFFSET = 12
LISTENING_POSITION_OFFSET = 13
# A literal `false` the writer always emits here. It reads no model field.
UNKNOWN_FLAG_OFFSET = 14
EQUALIZER_ENABLED_OFFSET = 15
BAND_COUNT_OFFSET = 16
BANK_IN_USE_OFFSET = 17

BANK_A_OFFSET = 18
BANK_B_OFFSET = 142
BANK_BAND_SLOTS = 31
BANK_BYTES = BANK_BAND_SLOTS * 4

# The unit keeps two equalizer banks and plays the one `bank_in_use`
# names. A real unit read 0 on 2026-10-08. Each bank has its own preset
# index, at PRESET_INDEX_A_OFFSET and PRESET_INDEX_B_OFFSET below.
BANK_A = 0
BANK_B = 1

PRESET_INDEX_A_OFFSET = 266
PRESET_INDEX_B_OFFSET = 267
BANK_FLAG_B_OFFSET = 268
BANK_FLAG_C_OFFSET = 269
SOUND_FIELD_OFFSET = 270

CROSSOVER_OFFSET = 271
CROSSOVER_SPEAKER_COUNT = 4

# Each record is one phase flag, then three float32. A hook on the app's own
# reader (`b/g/h.a(ByteArrayInputStream, model/b/w$a)`) under the Android
# emulator showed this. It logged the stream position before and after each
# call. Every one of the 7 calls reads 1 byte then 4+4+4, never the other
# order.
#
# An earlier version of this module read the floats first and a trailing
# "separator" byte last, offset by one record. The byte it called the separator
# of speaker N was the flag of speaker N+1. The real flag of speaker 0 (byte
# 279) never reached any record. See USB_CAPTURE_NOTES.md in the outer repo for
# the full trace.
SPEAKER_RECORD_OFFSET = 279
SPEAKER_RECORD_COUNT = 7
SPEAKER_RECORD_STRIDE = 13

CANCELLING_FLAG_A_OFFSET = 370
CANCELLING_FLAG_B_OFFSET = 371
CANCELLING_LEFT_OFFSET = 372
CANCELLING_RIGHT_OFFSET = 424
CANCELLING_BAND_COUNT = 13

MANUAL_LEFT_OFFSET = 476
MANUAL_RIGHT_OFFSET = 480

NAME_OFFSET = 484
NAME_BYTES = 32

SOURCE_TYPE_OFFSET = 516
BANK_TYPE_OFFSET = 517
MODEL_VALUE_OFFSET = 519
CAR_MODEL_NAME_KEY_DIGEST_OFFSET = 523
CAR_MODEL_NAME_KEY_DIGEST_BYTES = 16
TRAILING_FLAG_OFFSET = 539
TRAILING_BYTES_OFFSET = 540
TRAILING_BYTES = 32

# The order the blob reserves a record for, in a STANDARD speaker mode. A
# mode that does not drive a position still reserves its record, so the slot
# is a position in this list, not an enum ordinal.
STANDARD_SPEAKER_ORDER = (
    "FRONT_L", "FRONT_R", "REAR_L", "REAR_R", "REAR_L_SW", "REAR_R_SW", "SW",
)

# Which side of the crossover each speaker type uses. A front or rear speaker
# only ever gets a high pass, a subwoofer only ever a low pass.
CROSSOVER_SPEAKER_TYPES = (
    "STANDARD_FRONT", "STANDARD_REAR", "STANDARD_REARSW", "SUBWOOFER",
)


class BlobLengthError(ValueError):
    """Raised when a blob is not the length this module can read."""


@dataclass
class SpeakerRecord:
    """One speaker's phase flag and its three stored values.

    `is_positive_phase` is the one byte that the app's own reader takes before
    the three floats. A hook on that reader showed this (see the module
    docstring of `deq_blob.py`). All 7 speakers have this flag.

    The names of the three floats come from the app's own JSON writer
    (`i/d/c.smali`). It serializes this exact object as `{isPositivePhase,
    levelDB, timeAlignmentCm, levelDBExtended}`. The `Speaker` model in
    `eq_data.py` already has the same four keys.
    """

    is_positive_phase: bool = True
    level_db: float = 0.0
    time_alignment_cm: float = 0.0
    level_db_extended: float = 0.0


@dataclass
class CrossoverSetting:
    """One speaker type's stored crossover, as two enum positions."""

    frequency: int = 0
    slope: int = 0


@dataclass
class UserConfiguration:
    """The whole blob, field by field."""

    version: int = BLOB_VERSION
    timestamp_seconds: int = 0
    speaker_mode: int = 3
    listening_position: int = 2
    always_false_flag: int = 0
    equalizer_enabled: int = 0
    band_count: int = BANK_BAND_SLOTS
    bank_in_use: int = 0
    bank_a_gains_db: list[float] = field(
        default_factory=lambda: [0.0] * BANK_BAND_SLOTS
    )
    bank_b_gains_db: list[float] = field(
        default_factory=lambda: [0.0] * BANK_BAND_SLOTS
    )
    preset_index_a: int = 0
    preset_index_b: int = 0
    bank_flag_b: int = 1
    bank_flag_c: int = 0
    sound_field: int = 0
    crossovers: list[CrossoverSetting] = field(
        default_factory=lambda: [
            CrossoverSetting() for _ in range(CROSSOVER_SPEAKER_COUNT)
        ]
    )
    speakers: list[SpeakerRecord] = field(default_factory=lambda: _default_speakers())
    cancelling_flag_a: int = 0
    cancelling_flag_b: int = 0
    cancelling_left_db: list[float] = field(
        default_factory=lambda: [0.0] * CANCELLING_BAND_COUNT
    )
    cancelling_right_db: list[float] = field(
        default_factory=lambda: [0.0] * CANCELLING_BAND_COUNT
    )
    manual_left: float = 0.0
    manual_right: float = 0.0
    # 484..515. The preset JSON header's own `uniqueId` string, encoded by the
    # writer's string-to-bytes call. Zero when the profile carries none.
    #
    # `deq_session.py` never builds a configuration from scratch and writes it.
    # Every write path reads the unit's current blob first. So this default
    # never goes over the wire as it is. Keep it that way. A write path that
    # skips the read would zero out the unit's real uniqueId.
    unique_id_bytes: bytes = bytes(NAME_BYTES)
    source_type: int = 0xFF
    bank_type: int = 0
    model_value: int = 0
    # 523..538. MD5(carModelNameKey), or 16 zero bytes when no car model is
    # selected. See this module's docstring for the trace.
    car_model_name_key_digest: bytes = bytes(CAR_MODEL_NAME_KEY_DIGEST_BYTES)
    trailing_flag: int = 0
    trailing_bytes: bytes = bytes(TRAILING_BYTES)


def trim_gains_to_band_count(configuration: UserConfiguration) -> UserConfiguration:
    """Zeroes every band gain that the unit will ignore.

    The unit reads `band_count` bands and leaves the rest of the 31 slots
    alone. So the unit drops a gain above that count on its next write. This
    function, applied first, keeps the sent values and the returned values the
    same.
    """
    for gains in (configuration.bank_a_gains_db, configuration.bank_b_gains_db):
        for slot in range(configuration.band_count, BANK_BAND_SLOTS):
            gains[slot] = 0.0
    return configuration


def _default_speakers() -> list[SpeakerRecord]:
    """Returns one empty record per slot."""
    return [SpeakerRecord() for _ in range(SPEAKER_RECORD_COUNT)]


def _read_floats(blob: bytes, offset: int, count: int) -> list[float]:
    return list(struct.unpack_from(f"<{count}f", blob, offset))


def _write_floats(blob: bytearray, offset: int, values: list[float], count: int) -> None:
    if len(values) != count:
        raise ValueError(f"expected {count} values at offset {offset}, got {len(values)}")
    struct.pack_into(f"<{count}f", blob, offset, *values)


def decode_blob(blob: bytes) -> UserConfiguration:
    """Returns the configuration one STANDARD-mode blob holds."""
    if len(blob) != STANDARD_BLOB_BYTES:
        raise BlobLengthError(
            f"expected {STANDARD_BLOB_BYTES} bytes, got {len(blob)}; "
            "a NETWORK speaker mode writes a shorter blob and is not supported"
        )
    return UserConfiguration(
        version=int.from_bytes(blob[VERSION_OFFSET:VERSION_OFFSET + 4], "little"),
        timestamp_seconds=int.from_bytes(
            blob[TIMESTAMP_OFFSET:TIMESTAMP_OFFSET + 8], "little"
        ),
        speaker_mode=blob[SPEAKER_MODE_OFFSET],
        listening_position=blob[LISTENING_POSITION_OFFSET],
        always_false_flag=blob[UNKNOWN_FLAG_OFFSET],
        equalizer_enabled=blob[EQUALIZER_ENABLED_OFFSET],
        band_count=blob[BAND_COUNT_OFFSET],
        bank_in_use=blob[BANK_IN_USE_OFFSET],
        bank_a_gains_db=_read_floats(blob, BANK_A_OFFSET, BANK_BAND_SLOTS),
        bank_b_gains_db=_read_floats(blob, BANK_B_OFFSET, BANK_BAND_SLOTS),
        preset_index_a=blob[PRESET_INDEX_A_OFFSET],
        preset_index_b=blob[PRESET_INDEX_B_OFFSET],
        bank_flag_b=blob[BANK_FLAG_B_OFFSET],
        bank_flag_c=blob[BANK_FLAG_C_OFFSET],
        sound_field=blob[SOUND_FIELD_OFFSET],
        crossovers=[
            CrossoverSetting(
                frequency=blob[CROSSOVER_OFFSET + index * 2],
                slope=blob[CROSSOVER_OFFSET + index * 2 + 1],
            )
            for index in range(CROSSOVER_SPEAKER_COUNT)
        ],
        speakers=[_read_speaker_record(blob, slot) for slot in range(SPEAKER_RECORD_COUNT)],
        cancelling_flag_a=blob[CANCELLING_FLAG_A_OFFSET],
        cancelling_flag_b=blob[CANCELLING_FLAG_B_OFFSET],
        cancelling_left_db=_read_floats(
            blob, CANCELLING_LEFT_OFFSET, CANCELLING_BAND_COUNT
        ),
        cancelling_right_db=_read_floats(
            blob, CANCELLING_RIGHT_OFFSET, CANCELLING_BAND_COUNT
        ),
        manual_left=struct.unpack_from("<f", blob, MANUAL_LEFT_OFFSET)[0],
        manual_right=struct.unpack_from("<f", blob, MANUAL_RIGHT_OFFSET)[0],
        unique_id_bytes=blob[NAME_OFFSET:NAME_OFFSET + NAME_BYTES],
        source_type=blob[SOURCE_TYPE_OFFSET],
        bank_type=int.from_bytes(blob[BANK_TYPE_OFFSET:BANK_TYPE_OFFSET + 2], "little"),
        model_value=int.from_bytes(
            blob[MODEL_VALUE_OFFSET:MODEL_VALUE_OFFSET + 4], "little"
        ),
        car_model_name_key_digest=blob[
            CAR_MODEL_NAME_KEY_DIGEST_OFFSET
            :CAR_MODEL_NAME_KEY_DIGEST_OFFSET + CAR_MODEL_NAME_KEY_DIGEST_BYTES
        ],
        trailing_flag=blob[TRAILING_FLAG_OFFSET],
        trailing_bytes=blob[TRAILING_BYTES_OFFSET:TRAILING_BYTES_OFFSET + TRAILING_BYTES],
    )


def _read_speaker_record(blob: bytes, slot: int) -> SpeakerRecord:
    """Reads one speaker's phase flag, then levelDB, timeAlignmentCm,
    levelDBExtended, in that order."""
    start = SPEAKER_RECORD_OFFSET + slot * SPEAKER_RECORD_STRIDE
    is_positive_phase = blob[start] != 0
    level_db, time_alignment_cm, level_db_extended = struct.unpack_from(
        "<3f", blob, start + 1
    )
    return SpeakerRecord(
        is_positive_phase, level_db, time_alignment_cm, level_db_extended
    )


def encode_blob(configuration: UserConfiguration) -> bytes:
    """Returns the 572 bytes one configuration writes."""
    blob = bytearray(STANDARD_BLOB_BYTES)
    blob[VERSION_OFFSET:VERSION_OFFSET + 4] = configuration.version.to_bytes(4, "little")
    blob[TIMESTAMP_OFFSET:TIMESTAMP_OFFSET + 8] = (
        configuration.timestamp_seconds.to_bytes(8, "little")
    )
    blob[SPEAKER_MODE_OFFSET] = configuration.speaker_mode
    blob[LISTENING_POSITION_OFFSET] = configuration.listening_position
    blob[UNKNOWN_FLAG_OFFSET] = configuration.always_false_flag
    blob[EQUALIZER_ENABLED_OFFSET] = configuration.equalizer_enabled
    blob[BAND_COUNT_OFFSET] = configuration.band_count
    blob[BANK_IN_USE_OFFSET] = configuration.bank_in_use

    _write_floats(blob, BANK_A_OFFSET, configuration.bank_a_gains_db, BANK_BAND_SLOTS)
    _write_floats(blob, BANK_B_OFFSET, configuration.bank_b_gains_db, BANK_BAND_SLOTS)

    blob[PRESET_INDEX_A_OFFSET] = configuration.preset_index_a
    blob[PRESET_INDEX_B_OFFSET] = configuration.preset_index_b
    blob[BANK_FLAG_B_OFFSET] = configuration.bank_flag_b
    blob[BANK_FLAG_C_OFFSET] = configuration.bank_flag_c
    blob[SOUND_FIELD_OFFSET] = configuration.sound_field

    _write_crossovers(blob, configuration.crossovers)
    _write_speaker_records(blob, configuration.speakers)

    blob[CANCELLING_FLAG_A_OFFSET] = configuration.cancelling_flag_a
    blob[CANCELLING_FLAG_B_OFFSET] = configuration.cancelling_flag_b
    _write_floats(
        blob, CANCELLING_LEFT_OFFSET, configuration.cancelling_left_db,
        CANCELLING_BAND_COUNT,
    )
    _write_floats(
        blob, CANCELLING_RIGHT_OFFSET, configuration.cancelling_right_db,
        CANCELLING_BAND_COUNT,
    )
    struct.pack_into("<f", blob, MANUAL_LEFT_OFFSET, configuration.manual_left)
    struct.pack_into("<f", blob, MANUAL_RIGHT_OFFSET, configuration.manual_right)

    _write_fixed_bytes(blob, NAME_OFFSET, configuration.unique_id_bytes, NAME_BYTES, "unique id")
    blob[SOURCE_TYPE_OFFSET] = configuration.source_type
    blob[BANK_TYPE_OFFSET:BANK_TYPE_OFFSET + 2] = configuration.bank_type.to_bytes(
        2, "little"
    )
    blob[MODEL_VALUE_OFFSET:MODEL_VALUE_OFFSET + 4] = (
        configuration.model_value.to_bytes(4, "little")
    )
    _write_fixed_bytes(
        blob, CAR_MODEL_NAME_KEY_DIGEST_OFFSET, configuration.car_model_name_key_digest,
        CAR_MODEL_NAME_KEY_DIGEST_BYTES, "car model name key digest",
    )
    blob[TRAILING_FLAG_OFFSET] = configuration.trailing_flag
    _write_fixed_bytes(
        blob, TRAILING_BYTES_OFFSET, configuration.trailing_bytes,
        TRAILING_BYTES, "trailing bytes",
    )
    return bytes(blob)


def _write_crossovers(blob: bytearray, crossovers: list[CrossoverSetting]) -> None:
    if len(crossovers) != CROSSOVER_SPEAKER_COUNT:
        raise ValueError(
            f"expected {CROSSOVER_SPEAKER_COUNT} crossovers, got {len(crossovers)}"
        )
    for index, crossover in enumerate(crossovers):
        blob[CROSSOVER_OFFSET + index * 2] = crossover.frequency
        blob[CROSSOVER_OFFSET + index * 2 + 1] = crossover.slope


def _write_speaker_records(blob: bytearray, speakers: list[SpeakerRecord]) -> None:
    """Writes each speaker's phase flag and three floats, in that order."""
    if len(speakers) != SPEAKER_RECORD_COUNT:
        raise ValueError(
            f"expected {SPEAKER_RECORD_COUNT} speaker records, got {len(speakers)}"
        )
    for slot, speaker in enumerate(speakers):
        start = SPEAKER_RECORD_OFFSET + slot * SPEAKER_RECORD_STRIDE
        blob[start] = 1 if speaker.is_positive_phase else 0
        struct.pack_into(
            "<3f", blob, start + 1,
            speaker.level_db, speaker.time_alignment_cm, speaker.level_db_extended,
        )


def _write_fixed_bytes(
    blob: bytearray, offset: int, value: bytes, width: int, label: str
) -> None:
    if len(value) != width:
        raise ValueError(f"{label} must be {width} bytes, got {len(value)}")
    blob[offset:offset + width] = value
