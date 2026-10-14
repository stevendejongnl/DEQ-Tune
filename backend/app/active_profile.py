"""The profile the unit should play, and putting it on the unit.

A person activates one profile. The backend stores the choice and pushes the
profile at once when the unit is connected. When the unit is not connected,
the push waits: `DeqDevice` calls `apply_after_connect` each time a link comes
up, and the profile goes onto the unit then.

The status answers one question for the app: does the unit play this
profile now?
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from sqlmodel import Session

from app.db import engine
from app.deq_device import DeqDevice, DeviceUnavailable, device
from app.eq_data import TuningData
from app.models import ActiveProfileSetting, Profile
from app.schemas import ActiveProfileRead

SETTING_ROW_ID = 1


class ActiveStatus(str, Enum):
    NONE = "none"
    # The unit is not connected. The profile goes on when it connects.
    WAITING = "waiting"
    # The unit plays the stored version of this profile.
    APPLIED = "applied"
    # The unit is connected but does not play the stored version. A person
    # edited the profile after the push, or this link never got it.
    OUTDATED = "outdated"
    # The last push on this link failed. `problem` says why.
    FAILED = "failed"


def read_active_profile_id(session: Session) -> int | None:
    setting = session.get(ActiveProfileSetting, SETTING_ROW_ID)
    return None if setting is None else setting.profile_id


def write_active_profile_id(session: Session, profile_id: int | None) -> None:
    setting = session.get(ActiveProfileSetting, SETTING_ROW_ID) or ActiveProfileSetting(
        id=SETTING_ROW_ID
    )
    setting.profile_id = profile_id
    session.add(setting)
    session.commit()


@dataclass(frozen=True)
class PushRecord:
    """One push of a profile, on one link."""

    profile_id: int
    link_generation: int
    data: dict | None = None
    problem: str | None = None


class ActiveProfile:
    """Keeps the profile the unit should play, and puts it on the unit.

    A route calls `activate` and `state`. The device calls
    `apply_after_connect` each time a link comes up. It depends on the device
    and on a function that opens a database session.
    """

    def __init__(self, unit: DeqDevice, open_session: Callable[[], Session]) -> None:
        self.unit = unit
        self.open_session = open_session
        self._last_push: PushRecord | None = None

    def activate(self, profile_id: int) -> ActiveProfileRead:
        """Stores the choice, and pushes the profile when the unit is connected.

        Raises LookupError when no profile has that id.
        """
        with self.open_session() as session:
            if session.get(Profile, profile_id) is None:
                raise LookupError(f"no profile has id {profile_id}")
            write_active_profile_id(session, profile_id)
        if self.unit.state().connected:
            self._push(profile_id)
        return self.state()

    def apply_after_connect(self) -> None:
        """Pushes the active profile onto a link that just came up."""
        with self.open_session() as session:
            profile_id = read_active_profile_id(session)
        if profile_id is not None:
            self._push(profile_id)

    def state(self) -> ActiveProfileRead:
        with self.open_session() as session:
            profile_id = read_active_profile_id(session)
            profile = None if profile_id is None else session.get(Profile, profile_id)
            stored_data = None if profile is None else profile.data
        if profile_id is None or stored_data is None:
            return ActiveProfileRead(profile_id=None, status=ActiveStatus.NONE.value)
        if not self.unit.state().connected:
            return ActiveProfileRead(profile_id=profile_id, status=ActiveStatus.WAITING.value)
        push = self._last_push
        on_this_link = (
            push is not None
            and push.profile_id == profile_id
            and push.link_generation == self.unit.link_generation
        )
        if on_this_link and push.problem is not None:
            return ActiveProfileRead(
                profile_id=profile_id, status=ActiveStatus.FAILED.value, problem=push.problem
            )
        if on_this_link and push.data == stored_data:
            return ActiveProfileRead(profile_id=profile_id, status=ActiveStatus.APPLIED.value)
        return ActiveProfileRead(profile_id=profile_id, status=ActiveStatus.OUTDATED.value)

    def _push(self, profile_id: int) -> None:
        """Writes the stored profile to the unit, and records how it went.

        It never raises. A failed push is a status the app shows, and the next
        link tries again.

        It takes no lock of its own. `DeqDevice.write_tuning` holds the link
        lock for the whole push, and the connect hook calls this method with
        that lock already held. A second lock here would deadlock against it.
        """
        with self.open_session() as session:
            profile = session.get(Profile, profile_id)
            data = None if profile is None else copy.deepcopy(profile.data)
        if data is None:
            return
        link_generation = self.unit.link_generation
        try:
            self.unit.write_tuning(TuningData.model_validate(data))
        except (DeviceUnavailable, ValueError) as caught_error:
            self._last_push = PushRecord(profile_id, link_generation, problem=str(caught_error))
            return
        self._last_push = PushRecord(profile_id, link_generation, data=data)


def open_database_session() -> Session:
    return Session(engine)


# The app keeps one unit, so one active-profile keeper serves every request.
# `main.py` hooks it into the device's connect.
active_profile = ActiveProfile(device, open_database_session)
