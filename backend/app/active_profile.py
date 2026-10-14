"""What the unit should play, and putting it on the unit.

A person picks a car profile, an EQ on top of it, and a source mode. The
backend stores all three. It pushes the profile plus the EQ at once when the
unit is connected. When the unit is not connected, the push waits:
`DeqDevice` calls `apply_after_connect` each time a link comes up, and asks
`source_for_connect` which source mode to set first.

The status answers one question for the app: does the unit play this
profile and this EQ now?
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from sqlmodel import Session

from app.db import engine
from app.deq_device import DeqDevice, DeviceUnavailable, device
from app.deq_session import DEFAULT_AUDIO_SOURCE, DeqSession, DeviceStatusError
from app.eq_data import TuningData
from app.equalizers import with_equalizer
from app.models import ActiveProfileSetting, Equalizer, Profile
from app.schemas import ActiveProfileRead

SETTING_ROW_ID = 1


class ActiveStatus(str, Enum):
    NONE = "none"
    # The unit is not connected. The profile goes on when it connects.
    WAITING = "waiting"
    # The unit plays the stored versions of this profile and this EQ.
    APPLIED = "applied"
    # The unit is connected but plays something else. A person edited the
    # profile or the EQ after the push, chose another EQ, or this link never
    # got them.
    OUTDATED = "outdated"
    # The last push on this link failed. `problem` says why.
    FAILED = "failed"


def read_setting(session: Session) -> ActiveProfileSetting:
    """Returns the one setting row. A new database has none yet."""
    return session.get(ActiveProfileSetting, SETTING_ROW_ID) or ActiveProfileSetting(
        id=SETTING_ROW_ID
    )


def save_setting(session: Session, setting: ActiveProfileSetting) -> None:
    session.add(setting)
    session.commit()


def read_active_profile_id(session: Session) -> int | None:
    return read_setting(session).profile_id


def write_active_profile_id(session: Session, profile_id: int | None) -> None:
    setting = read_setting(session)
    setting.profile_id = profile_id
    save_setting(session, setting)


def read_active_equalizer_id(session: Session) -> int | None:
    return read_setting(session).equalizer_id


def write_active_equalizer_id(session: Session, equalizer_id: int | None) -> None:
    setting = read_setting(session)
    setting.equalizer_id = equalizer_id
    save_setting(session, setting)


@dataclass(frozen=True)
class Playable:
    """The stored profile and EQ, as one thing to push and to compare."""

    profile_id: int
    profile_data: dict
    equalizer_gains: list[float] | None


@dataclass(frozen=True)
class PushRecord:
    """One push, on one link."""

    link_generation: int
    playable: Playable | None = None
    profile_id: int | None = None
    problem: str | None = None


class ActiveProfile:
    """Keeps what the unit should play, and puts it on the unit.

    Routes call `activate`, `activate_equalizer`, `remember_source` and
    `state`. The device calls `source_for_connect` and `apply_after_connect`
    each time a link comes up. It depends on the device and on a function that
    opens a database session.
    """

    def __init__(self, unit: DeqDevice, open_session: Callable[[], Session]) -> None:
        self.unit = unit
        self.open_session = open_session
        self._last_push: PushRecord | None = None

    def activate(self, profile_id: int) -> ActiveProfileRead:
        """Stores the car profile, and pushes when the unit is connected.

        Raises LookupError when no profile has that id.
        """
        with self.open_session() as session:
            if session.get(Profile, profile_id) is None:
                raise LookupError(f"no profile has id {profile_id}")
            write_active_profile_id(session, profile_id)
        self._push_if_connected()
        return self.state()

    def activate_equalizer(self, equalizer_id: int | None) -> ActiveProfileRead:
        """Stores the EQ, and pushes when the unit is connected.

        `None` plays the car profile alone. Raises LookupError when no EQ has
        that id.
        """
        with self.open_session() as session:
            if equalizer_id is not None and session.get(Equalizer, equalizer_id) is None:
                raise LookupError(f"no EQ has id {equalizer_id}")
            write_active_equalizer_id(session, equalizer_id)
        self._push_if_connected()
        return self.state()

    def remember_source(self, source_name: str) -> None:
        """Stores the source mode that each new link gets."""
        with self.open_session() as session:
            setting = read_setting(session)
            setting.source_mode = source_name
            save_setting(session, setting)

    def choose_source(self, source_name: str) -> ActiveProfileRead:
        """Stores the source mode, and sets it now when the unit is connected.

        A unit that is not connected gets it on the next link. A failed write
        keeps the choice too, for the same reason.
        """
        self.remember_source(source_name)
        if self.unit.state().connected:
            try:
                self.unit.run(lambda session: switch_source(session, source_name))
            except DeviceUnavailable:
                pass
        return self.state()

    def source_for_connect(self) -> str:
        with self.open_session() as session:
            return read_setting(session).source_mode or DEFAULT_AUDIO_SOURCE

    def apply_after_connect(self) -> None:
        """Pushes the active profile and EQ onto a link that just came up."""
        playable = self._stored_playable()
        if playable is not None:
            self._push(playable)

    def state(self) -> ActiveProfileRead:
        with self.open_session() as session:
            setting = read_setting(session)
        playable = self._stored_playable()
        base = {
            "equalizer_id": setting.equalizer_id,
            "source_mode": setting.source_mode or DEFAULT_AUDIO_SOURCE,
        }
        if playable is None:
            return ActiveProfileRead(profile_id=None, status=ActiveStatus.NONE.value, **base)
        profile_id = playable.profile_id
        if not self.unit.state().connected:
            return ActiveProfileRead(
                profile_id=profile_id, status=ActiveStatus.WAITING.value, **base
            )
        push = self._last_push
        on_this_link = push is not None and push.link_generation == self.unit.link_generation
        if on_this_link and push.problem is not None and push.profile_id == profile_id:
            return ActiveProfileRead(
                profile_id=profile_id,
                status=ActiveStatus.FAILED.value,
                problem=push.problem,
                **base,
            )
        if on_this_link and push.playable == playable:
            return ActiveProfileRead(
                profile_id=profile_id, status=ActiveStatus.APPLIED.value, **base
            )
        return ActiveProfileRead(profile_id=profile_id, status=ActiveStatus.OUTDATED.value, **base)

    def _stored_playable(self) -> Playable | None:
        with self.open_session() as session:
            setting = read_setting(session)
            profile = None if setting.profile_id is None else session.get(Profile, setting.profile_id)
            if profile is None:
                return None
            equalizer = (
                None if setting.equalizer_id is None else session.get(Equalizer, setting.equalizer_id)
            )
            return Playable(
                profile_id=profile.id,
                profile_data=copy.deepcopy(profile.data),
                equalizer_gains=None if equalizer is None else list(equalizer.gains),
            )

    def _push_if_connected(self) -> None:
        playable = self._stored_playable()
        if playable is not None and self.unit.state().connected:
            self._push(playable)

    def _push(self, playable: Playable) -> None:
        """Writes the profile plus the EQ to the unit, and records how it went.

        It never raises. A failed push is a status the app shows, and the next
        link tries again.

        It takes no lock of its own. `DeqDevice.run` holds the link lock for
        the whole push, and the connect hook calls this method with that lock
        already held. A second lock here would deadlock against it.
        """
        link_generation = self.unit.link_generation
        try:
            tuning = TuningData.model_validate(playable.profile_data)
            if playable.equalizer_gains is not None:
                tuning = with_equalizer(tuning, playable.equalizer_gains)
            self.unit.run(lambda session: write_playable(session, tuning))
        except (DeviceUnavailable, ValueError) as caught_error:
            self._last_push = PushRecord(
                link_generation, profile_id=playable.profile_id, problem=str(caught_error)
            )
            return
        self._last_push = PushRecord(link_generation, playable=playable)


def switch_source(session: DeqSession, source_name: str) -> None:
    """Writes the mode, then says the device is ready, as the app does.

    A mode change on its own leaves the car silent until PLAY_READY follows it.
    See `DeqSession.start`.
    """
    session.set_audio_source(source_name)
    session.notify_play_ready()


def write_playable(session: DeqSession, tuning: TuningData) -> None:
    """Sends the tuning, then puts the unit's own style on Custom A.

    A refused style write leaves the coefficients in place, and those are what
    the unit plays. So that refusal does not fail the push.
    """
    session.write_tuning(tuning)
    try:
        session.use_custom_bank_a()
    except DeviceStatusError:
        pass


def open_database_session() -> Session:
    return Session(engine)


# The app keeps one unit, so one active-profile keeper serves every request.
# `main.py` hooks it into the device's connect.
active_profile = ActiveProfile(device, open_database_session)
