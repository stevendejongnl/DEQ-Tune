"""Turns the unit's settings blob into a profile's tuning.

The Pioneer app writes its profile model into the blob (`b/g/h.a(z, Z, o)`
in the decompiled APK). So the blob holds a profile, and this module reads
one back out. Each field below follows the app's own writer and its JSON
writer (`i/d/c.smali`), which names the profile key of every model field.

The blob keeps a few things a profile does not: the subwoofer records, the
stored filters past front and rear (such as the subwoofer's low pass),
and the lock. This module leaves
them on the unit. A push of the profile does not touch them either.
"""

from __future__ import annotations

from app.deq_blob import UserConfiguration
from app.deq_dsp import (
    EQUALIZER_BAND_COUNT,
    WIDE_BAND_COUNT,
    convert_wide_bands_to_equalizer_bands,
)
from app.eq_data import (
    CancellingEq,
    CancellingTA,
    FactoryCancel,
    FactoryCancelData,
    FaderBalance,
    Filter,
    FilterBand,
    FoundationEq,
    LRBank,
    Speaker,
    TimeAlignment,
    TuningData,
)

# The blob reserves speaker records in this order (`STANDARD_SPEAKER_ORDER`).
# A profile names the first four.
PROFILE_SPEAKER_RECORDS = {"FL": 0, "FR": 1, "RL": 2, "RR": 3}

FRONT_CROSSOVER_SLOT = 0
REAR_CROSSOVER_SLOT = 1


def tuning_from_configuration(configuration: UserConfiguration) -> TuningData:
    """Returns the profile that one settings blob holds."""
    return TuningData(
        foundationEq=_foundation_equalizer(configuration),
        speakers={
            channel: _speaker(configuration, record)
            for channel, record in PROFILE_SPEAKER_RECORDS.items()
        },
        filter=Filter(
            front=_filter_band(configuration, FRONT_CROSSOVER_SLOT),
            rear=_filter_band(configuration, REAR_CROSSOVER_SLOT),
        ),
        factoryCancel=_factory_cancel(configuration),
        faderBalance=FaderBalance(fader=0, balance=0),
        timeAlignment=TimeAlignment(
            enabled=True, easySoundFitModeEnabled=False, easySoundFitMode=-1
        ),
    )


def _foundation_equalizer(configuration: UserConfiguration) -> FoundationEq:
    """Puts both banks into the one LR slot, as 13 bands each.

    The editor and the push both work in 13 bands. A 31-band bank goes through
    the app's own conversion here. The push would do the same conversion, so
    the unit gets the same coefficients either way.
    """
    banks = [
        _equalizer_bank(configuration.bank_a_gains_db, configuration.band_count),
        _equalizer_bank(configuration.bank_b_gains_db, configuration.band_count),
    ]
    return FoundationEq(
        isLRMode=False,
        eqs={
            "LR": LRBank(
                isLocked=False,
                numOfBand=EQUALIZER_BAND_COUNT,
                selectedBank=configuration.bank_in_use,
                banks=banks,
            )
        },
        expandEq={},
    )


def _equalizer_bank(slot_gains_db: list[float], band_count: int) -> list[float]:
    if band_count == WIDE_BAND_COUNT:
        return convert_wide_bands_to_equalizer_bands(slot_gains_db)
    if band_count == EQUALIZER_BAND_COUNT:
        return list(slot_gains_db[:EQUALIZER_BAND_COUNT])
    raise ValueError(f"the unit holds a {band_count}-band equalizer")


def _speaker(configuration: UserConfiguration, record: int) -> Speaker:
    stored = configuration.speakers[record]
    return Speaker(
        isPositivePhase=stored.is_positive_phase,
        levelDB=stored.level_db,
        timeAlignmentCm=stored.time_alignment_cm,
        levelDBExtended=stored.level_db_extended,
    )


def _filter_band(configuration: UserConfiguration, slot: int) -> FilterBand:
    """Reads one crossover slot as a profile's high-pass filter.

    The blob stores the same positions that a profile's `cutoff_hpf` and
    `slope_hpf` hold. `DeqSession.write_crossover` turns a profile's band
    into a stored filter the same way.
    """
    stored = configuration.crossovers[slot]
    return FilterBand(cutoff_hpf=stored.frequency, slope_hpf=stored.slope)


def _factory_cancel(configuration: UserConfiguration) -> FactoryCancel:
    return FactoryCancel(
        available=configuration.cancelling_available != 0,
        enabled=configuration.cancelling_enabled != 0,
        data=FactoryCancelData(
            cancellingEQ=CancellingEq(
                L=list(configuration.cancelling_left_db),
                R=list(configuration.cancelling_right_db),
            ),
            cancellingTACm=CancellingTA(
                L=configuration.cancelling_time_alignment_left_cm,
                R=configuration.cancelling_time_alignment_right_cm,
            ),
        ),
    )
