"""The HTTP face of the active profile.

The app marks one profile as the one the unit plays. `active_profile.py`
stores the choice and puts the profile on the unit.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.active_profile import ActiveProfile, active_profile
from app.schemas import ActiveProfileRead, ActiveProfileWrite

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
