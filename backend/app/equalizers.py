"""Music-style EQs, and how one goes on top of the car profile.

A profile describes the car: speakers, distances, filters and a correction
curve. An EQ describes a taste in music. The unit plays the sum of both.

The Pioneer app works the same way. `_makeOpalEQRequest` adds the profile's
curve and the app's own "makeup EQ" band for band, before it designs the
filters (`service/f.a(p$b, float[], float[])`). Each term and the sum go
through `f.b(float)`, which clamps to ±12 dB.
"""

from __future__ import annotations

from sqlmodel import Session, select

from app.deq_dsp import EQUALIZER_BAND_COUNT
from app.deq_session import selected_band_gains_db
from app.eq_data import TuningData
from app.models import Equalizer

GAIN_LIMIT_DB = 12.0

FLAT = [0.0] * EQUALIZER_BAND_COUNT

# The EQs that come with the app. Pioneer's own styles join them once their
# curves come out of the player library.
FACTORY_EQUALIZERS: dict[str, list[float]] = {"Flat": FLAT}


def clamp_gain(gain_db: float) -> float:
    return max(-GAIN_LIMIT_DB, min(GAIN_LIMIT_DB, gain_db))


def combine_curves(car_gains_db: list[float], style_gains_db: list[float]) -> list[float]:
    """Returns the curve the unit plays: the car's curve plus the style's.

    It clamps each term and the sum, as `service/f.a` in the app does.
    """
    return [
        clamp_gain(clamp_gain(car) + clamp_gain(style))
        for car, style in zip(car_gains_db, style_gains_db, strict=True)
    ]


def with_equalizer(tuning: TuningData, style_gains_db: list[float]) -> TuningData:
    """Returns a copy of the tuning whose selected bank holds the sum.

    The car's curve comes from `selected_band_gains_db`, so a 31-band bank
    becomes 13 bands first, as it does on every push.
    """
    combined = combine_curves(selected_band_gains_db(tuning), style_gains_db)
    result = tuning.model_copy(deep=True)
    slots = result.foundationEq.eqs
    slot = slots.get("LR") or next(iter(slots.values()))
    slot.banks[slot.selectedBank] = combined
    slot.numOfBand = EQUALIZER_BAND_COUNT
    return result


def seed_factory_equalizers(session: Session) -> int:
    """Inserts each factory EQ that the database lacks. Returns the count.

    Safe to call on every startup. It never changes an EQ that exists.
    """
    existing = set(
        session.exec(select(Equalizer.name).where(Equalizer.source == "factory")).all()
    )
    inserted = 0
    for name, gains in FACTORY_EQUALIZERS.items():
        if name in existing:
            continue
        session.add(Equalizer(name=name, source="factory", gains=list(gains)))
        inserted += 1
    if inserted:
        session.commit()
    return inserted
