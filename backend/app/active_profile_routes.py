"""The HTTP face of the active profile.

The app marks one profile as the one the unit plays. `active_profile.py`
stores the choice and puts the profile on the unit.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.active_profile import ActiveProfile, active_profile
from app.deq_enums import AUDIO_SOURCE
from app.schemas import (
    ActiveEqualizerWrite,
    ActiveProfileRead,
    ActiveProfileWrite,
    ActiveSourceWrite,
)

router = APIRouter(prefix="/active-profile", tags=["active-profile"])


def get_active_profile() -> ActiveProfile:
    """Returns the one active-profile keeper. A test overrides this dependency."""
    return active_profile


@router.get("", response_model=ActiveProfileRead)
def read_active_profile(keeper: ActiveProfile = Depends(get_active_profile)) -> ActiveProfileRead:
    return keeper.state()


@router.put("", response_model=ActiveProfileRead)
def activate_profile(
    body: ActiveProfileWrite, keeper: ActiveProfile = Depends(get_active_profile)
) -> ActiveProfileRead:
    """Makes one profile the active one, and pushes it when the unit is connected.

    A second call with the same profile pushes it again. That is how the app
    applies edits that came after the last push. A failed push answers 200 with
    status failed: the choice still holds, and the next link tries again.
    """
    try:
        return keeper.activate(body.profile_id)
    except LookupError as caught_error:
        raise HTTPException(status_code=404, detail=str(caught_error)) from caught_error


@router.put("/source", response_model=ActiveProfileRead)
def choose_source(
    body: ActiveSourceWrite, keeper: ActiveProfile = Depends(get_active_profile)
) -> ActiveProfileRead:
    """Picks the source mode for now and for every new link.

    Unlike `POST /device/audio-source`, it answers 200 while the unit is not
    connected. The choice then waits for the next link. The car app uses it
    for that reason.
    """
    if body.name not in AUDIO_SOURCE.names:
        raise HTTPException(status_code=422, detail=f"unknown audio source {body.name}")
    return keeper.choose_source(body.name)


@router.put("/equalizer", response_model=ActiveProfileRead)
def activate_equalizer(
    body: ActiveEqualizerWrite, keeper: ActiveProfile = Depends(get_active_profile)
) -> ActiveProfileRead:
    """Picks the EQ that plays on top of the car profile, and pushes both.

    `null` plays the car profile alone. A second call with the same EQ
    pushes again, as with the profile.
    """
    try:
        return keeper.activate_equalizer(body.equalizer_id)
    except LookupError as caught_error:
        raise HTTPException(status_code=404, detail=str(caught_error)) from caught_error
