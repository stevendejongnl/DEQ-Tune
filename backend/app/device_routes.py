"""The HTTP face of the DEQ unit.

The backend owns the USB link, so the frontend asks these endpoints what
the unit is and tells them what to send it. Each handler does one thing and
hands the work to `deq_device`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.deq_device import DeqDevice, DeviceUnavailable, device
from app.deq_session import DeviceStatusError
from app.eq_data import TuningData
from app.models import Profile
from app.schemas import (
    AudioSourceWrite,
    ProfileRead,
    UnitProfileCreate,
    AudioStateRead,
    DeviceOptionsRead,
    DeviceRead,
    EqStyleWrite,
    LiveSimulationWrite,
    MuteWrite,
    VolumeWrite,
    device_options,
)
from app.deq_enums import AUDIO_SOURCE
from app.unit_tuning import tuning_from_configuration
from app.active_profile import ActiveProfile, switch_source
from app.active_profile_routes import get_active_profile

router = APIRouter(prefix="/device", tags=["device"])

# The mute read and write carry a boolean: 1 is muted, 0 plays. See
# `DeqSession.set_mute_state`.
MUTED_WIRE_VALUE = 1

# 503, not 500: an unplugged unit is a normal state, and no bug.
DEVICE_UNAVAILABLE_STATUS = 503


def get_device() -> DeqDevice:
    """Returns the one device object. A test overrides this dependency."""
    return device


@router.get("", response_model=DeviceRead)
def read_device(unit: DeqDevice = Depends(get_device)) -> DeviceRead:
    """Returns what the header shows. This never opens a link itself."""
    return DeviceRead(**vars(unit.state()))


@router.post("/connect", response_model=DeviceRead)
def connect_device(unit: DeqDevice = Depends(get_device)) -> DeviceRead:
    """Opens the link and runs the unit's startup sequence.

    `LinkKeeper` connects by itself, so the frontend does not call this route.
    This route reports a failure in the body, and not as an error status. An
    unplugged unit is a normal state, and not a broken request.
    """
    return DeviceRead(**vars(unit.connect()))


@router.post("/disconnect", response_model=DeviceRead)
def disconnect_device(unit: DeqDevice = Depends(get_device)) -> DeviceRead:
    unit.disconnect()
    return DeviceRead(**vars(unit.state()))


@router.get("/audio", response_model=AudioStateRead)
def read_audio_state(unit: DeqDevice = Depends(get_device)) -> AudioStateRead:
    """Reads what the unit is doing with sound, live from the unit.

    Four reads in one action, so they share one lock and give one consistent
    picture. Four separate reads could interleave with another caller.

    This route stays out of `GET /api/device` on purpose. The header polls that
    route, and it never opens a link. These reads cost USB exchanges.
    """
    return run_on_unit(lambda: unit.run(_read_audio_state))


def _wire_name(enum, wire_value: int) -> str:
    """Names a wire value, or says plainly that the app declares no such value.

    A real unit answered the mute read with 0 on 2026-10-10, and the mute
    enum holds only -1, 1 and 2. Raising there turned one odd field into a
    failed read of all four, so the panel showed nothing at all. The raw
    number travels in the response too, so what the unit said stays visible.
    """
    try:
        return enum.by_wire_value(wire_value).name
    except KeyError:
        return f"UNKNOWN_{wire_value}"


def _read_audio_state(session) -> AudioStateRead:
    mode_wire = session.read_mode()
    volume_db = session.read_volume()
    mute_wire = session.read_mute_state()
    driving_wire = session.read_driving_state()
    return AudioStateRead(
        source_mode=_wire_name(AUDIO_SOURCE, mode_wire),
        source_mode_wire=mode_wire,
        volume_db=volume_db,
        muted=mute_wire == MUTED_WIRE_VALUE,
        mute_state_wire=mute_wire,
        driving=driving_wire == 1,
    )


@router.post("/volume", response_model=AudioStateRead)
def set_volume(
    body: VolumeWrite, unit: DeqDevice = Depends(get_device)
) -> AudioStateRead:
    """Sets the master volume, in dB.

    The unit refuses a volume write with STATUS -6 while it holds THROUGH, and
    takes one on an OTHER mode. Nobody measured CAR_SOURCE yet. So this route
    writes first. Only a refusal makes it move the mode, write again, and put
    the mode back. The refusal must not escape: `DeqDevice.run` drops the link
    on any session error, and a refused volume is no broken link.
    `scripts/probe_audio_output.py` does the same dance. A mode change cuts
    the audio for a moment, so the route avoids one that the unit does not
    need.
    """

    def action(session) -> AudioStateRead:
        original_wire = session.read_mode()
        original = AUDIO_SOURCE.by_wire_value(original_wire).name
        if original != "THROUGH":
            try:
                session.set_volume(body.volume_db)
                return _read_audio_state(session)
            except DeviceStatusError:
                pass
        session.set_audio_source("SP_OTHER_SOURCE")
        try:
            session.set_volume(body.volume_db)
        finally:
            # Always put the mode back, also when the write fails. A unit left
            # on SP_OTHER_SOURCE plays whatever this device writes, which is
            # silence. This endpoint exists to get people out of that failure.
            session.set_audio_source(original)
            # A return to the car's mode is not enough. Without PLAY_READY the
            # car stays silent after the mode comes back, the same way a fresh
            # connect did before `start` sent it. A slider move cut the audio
            # for this reason.
            session.notify_play_ready()
        return _read_audio_state(session)

    return run_on_unit(lambda: unit.run(action))


@router.post("/play-ready", response_model=AudioStateRead)
def send_play_ready(unit: DeqDevice = Depends(get_device)) -> AudioStateRead:
    """Tells the unit this device is ready to play audio (0x1a).

    The real app sends it at the end of every cold start, and so does the
    connect sequence here. Without it the car stayed silent for as long as the
    Pi stayed attached. Sent alone in a car on 2026-10-11, it brought the audio
    back at once. This endpoint stays as a lever for a link that is up but
    silent. It has no body and the reply is a status only.
    """
    return run_on_unit(
        lambda: unit.run(
            lambda session: (session.notify_play_ready(), _read_audio_state(session))[1]
        )
    )


@router.post("/audio-source", response_model=AudioStateRead)
def set_audio_source(
    body: AudioSourceWrite,
    unit: DeqDevice = Depends(get_device),
    keeper: ActiveProfile = Depends(get_active_profile),
) -> AudioStateRead:
    """Picks which input the unit plays, and keeps it for the next links.

    CAR_SOURCE plays the car's own audio through the DSP. THROUGH most likely
    skips the DSP. The backend sets the stored mode on every new link.
    """
    if body.name not in AUDIO_SOURCE.names:
        raise HTTPException(status_code=422, detail=f"unknown audio source {body.name}")
    state = run_on_unit(
        lambda: unit.run(
            lambda session: _switch_source(session, body.name)
        )
    )
    keeper.remember_source(body.name)
    return state


def _switch_source(session, name: str) -> AudioStateRead:
    switch_source(session, name)
    return _read_audio_state(session)


@router.post("/mute", response_model=AudioStateRead)
def set_mute(body: MuteWrite, unit: DeqDevice = Depends(get_device)) -> AudioStateRead:
    """Mutes or unmutes the unit, and answers with what it now holds."""

    def action(session) -> AudioStateRead:
        session.set_mute_state(body.muted)
        return _read_audio_state(session)

    return run_on_unit(lambda: unit.run(action))

@router.get("/options", response_model=DeviceOptionsRead)
def read_device_options() -> DeviceOptionsRead:
    """Returns the value sets the unit accepts, read from the Pioneer app."""
    return device_options()


@router.post("/tuning/{profile_id}", response_model=DeviceRead)
def write_tuning(
    profile_id: int,
    unit: DeqDevice = Depends(get_device),
    session: Session = Depends(get_session),
) -> DeviceRead:
    """Sends one stored profile's DSP settings to the unit."""
    profile = session.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not found")
    # The column stores the tuning as plain JSON. So check it before the DSP
    # code reads it by attribute.
    tuning = TuningData.model_validate(profile.data)
    run_on_unit(lambda: unit.write_tuning(tuning))
    return DeviceRead(**vars(unit.state()))


@router.post("/profile", response_model=ProfileRead, status_code=201)
def save_unit_profile(
    body: UnitProfileCreate,
    unit: DeqDevice = Depends(get_device),
    session: Session = Depends(get_session),
) -> Profile:
    """Reads the tune the unit holds now and stores it as a custom profile.

    A unit that a Pioneer app tuned keeps that tune in its settings blob. This
    route turns the blob into a profile, so a person keeps that tune before
    a push replaces it.
    """
    configuration = run_on_unit(unit.read_configuration)
    try:
        tuning = tuning_from_configuration(configuration)
    except ValueError as caught_error:
        raise HTTPException(status_code=409, detail=str(caught_error)) from caught_error
    profile = Profile(
        name=body.name,
        source="custom",
        data=tuning.model_dump(mode="json"),
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


@router.post("/eq-style", response_model=DeviceRead)
def select_eq_style(
    body: EqStyleWrite, unit: DeqDevice = Depends(get_device)
) -> DeviceRead:
    """Picks one of the unit's own EQ styles."""
    run_on_unit(lambda: unit.run(lambda session: session.select_eq_style(body.name)))
    return DeviceRead(**vars(unit.state()))


@router.post("/live-simulation", response_model=DeviceRead)
def select_live_simulation(
    body: LiveSimulationWrite, unit: DeqDevice = Depends(get_device)
) -> DeviceRead:
    """Picks one of the unit's own live-simulation modes."""
    run_on_unit(
        lambda: unit.run(lambda session: session.select_live_simulation(body.name))
    )
    return DeviceRead(**vars(unit.state()))


def run_on_unit(action):
    """Runs one action, and turns an unreachable unit into a 503.

    A bad value name is the caller's mistake, so it answers 400 instead.

    Returns whatever the action returned. The existing callers write to the
    unit and then build their own reply from `unit.state()`, so they ignore the
    return value. The audio endpoints read from the unit and need it.
    """
    try:
        return action()
    except DeviceUnavailable as caught_error:
        raise HTTPException(
            status_code=DEVICE_UNAVAILABLE_STATUS, detail=str(caught_error)
        ) from caught_error
    except KeyError as caught_error:
        raise HTTPException(status_code=400, detail=str(caught_error)) from caught_error
