"""The unit's crossover, for the Filter screen.

The unit stores one filter per speaker type. Its speaker mode decides which
of them play (`unit_crossover.py`). A car profile sets the front and rear
high-pass filters, and the unit keeps the rest. So these routes show every
filter the mode uses, and change only the ones the unit keeps. They also
change the speaker mode itself, within the STANDARD modes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.active_profile import ActiveProfile
from app.active_profile_routes import get_active_profile
from app.deq_blob import CrossoverSetting as StoredFilter
from app.deq_blob import UserConfiguration
from app.deq_device import DeqDevice
from app.deq_dsp import CROSSOVER_CUTOFFS_HZ, CROSSOVER_HIGH_CUTOFFS_HZ
from app.deq_enums import SPEAKER_MODE
from app.device_routes import get_device, run_on_unit
from app.schemas import (
    CrossoverFilterRead,
    CrossoverFilterWrite,
    CrossoverRead,
    SpeakerModeWrite,
)
from app.unit_crossover import (
    CROSSOVER_MAPS,
    STORED_FILTER_NAMES,
    STORED_FRONT,
    STORED_REAR,
    UnsupportedSpeakerModeError,
    filter_roles,
)

router = APIRouter(prefix="/device/crossover", tags=["device"])

PROFILE_OWNED = (STORED_FRONT, STORED_REAR)

# 409: the unit is reachable, but its speaker mode has no map yet.
UNSUPPORTED_MODE_STATUS = 409


@router.get("", response_model=CrossoverRead)
def read_crossover(
    unit: DeqDevice = Depends(get_device),
    active: ActiveProfile = Depends(get_active_profile),
) -> CrossoverRead:
    """Reads the unit's crossover, with the active profile's two filters."""
    configuration = run_on_unit(unit.read_configuration)
    return crossover_read(configuration, active.profile_filters())


@router.put("", response_model=CrossoverRead)
def write_crossover_filter(
    body: CrossoverFilterWrite,
    unit: DeqDevice = Depends(get_device),
    active: ActiveProfile = Depends(get_active_profile),
) -> CrossoverRead:
    """Changes one filter that the unit keeps, and plays it at once.

    A filter that the unit's speaker mode does not use answers 409. The unit
    would store it and play nothing different.
    """
    stored_index = STORED_FILTER_NAMES.index(body.speaker)
    stored_filter = StoredFilter(frequency=body.cutoff_position, slope=body.slope)
    front_and_rear = active.profile_filters()

    def change_filter(session) -> UserConfiguration:
        used = {role.stored_index for role in filter_roles(session.read_user_configuration().speaker_mode)}
        if stored_index not in used:
            raise UnusedFilterError(f"the speaker mode does not use the {body.speaker} filter")
        return session.write_stored_filter(stored_index, stored_filter, front_and_rear)

    try:
        configuration = run_on_unit(lambda: unit.run(change_filter))
    except (UnsupportedSpeakerModeError, UnusedFilterError) as caught_error:
        raise HTTPException(
            status_code=UNSUPPORTED_MODE_STATUS, detail=str(caught_error)
        ) from caught_error
    return crossover_read(configuration, front_and_rear)


class UnusedFilterError(ValueError):
    """Raised for a filter that the unit's speaker mode does not play."""


@router.put("/speaker-mode", response_model=CrossoverRead)
def change_speaker_mode(
    body: SpeakerModeWrite,
    unit: DeqDevice = Depends(get_device),
    active: ActiveProfile = Depends(get_active_profile),
) -> CrossoverRead:
    """Moves the unit to another speaker mode, and sends the push that goes with it."""
    speaker_mode = SPEAKER_MODE.by_name(body.speaker_mode).wire_value
    configuration = run_on_unit(lambda: active.change_speaker_mode(speaker_mode))
    return crossover_read(configuration, active.profile_filters())


def crossover_read(
    configuration: UserConfiguration,
    front_and_rear: tuple[StoredFilter, StoredFilter] | None,
) -> CrossoverRead:
    """Describes the filters that the unit's speaker mode uses.

    Raises a 409 for a speaker mode that has no map.
    """
    try:
        roles = filter_roles(configuration.speaker_mode)
    except UnsupportedSpeakerModeError as caught_error:
        raise HTTPException(
            status_code=UNSUPPORTED_MODE_STATUS, detail=str(caught_error)
        ) from caught_error
    stored_filters = list(configuration.crossovers)
    if front_and_rear is not None:
        stored_filters[STORED_FRONT], stored_filters[STORED_REAR] = front_and_rear
    return CrossoverRead(
        speaker_mode=SPEAKER_MODE.by_wire_value(configuration.speaker_mode).name,
        speaker_modes=list(CROSSOVER_MAPS),
        filters=[
            CrossoverFilterRead(
                speaker=STORED_FILTER_NAMES[role.stored_index],
                kind=role.kind.value,
                owner="profile" if role.stored_index in PROFILE_OWNED else "unit",
                cutoff_position=stored_filters[role.stored_index].frequency,
                slope=stored_filters[role.stored_index].slope,
                cutoffs_hz=[
                    float(cutoff)
                    for cutoff in (
                        CROSSOVER_HIGH_CUTOFFS_HZ
                        if role.uses_high_range
                        else CROSSOVER_CUTOFFS_HZ
                    )
                ],
            )
            for role in roles
        ],
    )
