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
from app.eq_data import TuningData
from app.models import Profile
from app.schemas import (
    AudioSourceWrite,
    AudioStateRead,
    DeviceOptionsRead,
    DeviceRead,
    EqStyleWrite,
    LiveSimulationWrite,
    VolumeWrite,
    device_options,
)
from app.deq_enums import AUDIO_SOURCE, MUTE_STATE

router = APIRouter(prefix="/device", tags=["device"])

# 503, not 500: the unit being unplugged is a normal state, not a bug.
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

    A failure is reported in the body, not as an error status: the frontend
    shows the reason in the header rather than treating it as a broken
    request.
    """
    return DeviceRead(**vars(unit.connect()))


@router.post("/disconnect", response_model=DeviceRead)
def disconnect_device(unit: DeqDevice = Depends(get_device)) -> DeviceRead:
    unit.disconnect()
    return DeviceRead(**vars(unit.state()))


@router.get("/audio", response_model=AudioStateRead)
def read_audio_state(unit: DeqDevice = Depends(get_device)) -> AudioStateRead:
    """Reads what the unit is doing with sound, live from the unit.

    Four reads in one action, so they are one lock and one consistent
    picture rather than four that can interleave with another caller.

    This is not part of `GET /api/device` on purpose: that one is polled
    by the header and never opens a link, and these cost USB exchanges.
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
        muted=mute_wire == MUTE_STATE.by_name("SOUND_OFF").wire_value,
        mute_state_wire=mute_wire,
        driving=driving_wire == 1,
    )


@router.post("/volume", response_model=AudioStateRead)
def set_volume(
    body: VolumeWrite, unit: DeqDevice = Depends(get_device)
) -> AudioStateRead:
    """Sets the master volume, in dB.

    The unit refuses a volume write with STATUS -6 while it holds
    THROUGH, and takes one on an OTHER mode, so this moves the mode,
    writes, and puts the mode back. That is the same dance
    `scripts/probe_audio_output.py` does, and the reason a volume could
    not be set from the app before.
    """

    def action(session) -> AudioStateRead:
        original_wire = session.read_mode()
        original = AUDIO_SOURCE.by_wire_value(original_wire).name
        if original == "THROUGH":
            session.set_audio_source("SP_OTHER_SOURCE")
        try:
            session.set_volume(body.volume_db)
        finally:
            # Always put the mode back, including when the write fails.
            # Leaving the unit on SP_OTHER_SOURCE plays whatever this
            # device writes, which is silence -- the exact failure this
            # endpoint exists to get people out of.
            if original == "THROUGH":
                session.set_audio_source(original)
        return _read_audio_state(session)

    return run_on_unit(lambda: unit.run(action))


@router.post("/play-ready", response_model=AudioStateRead)
def send_play_ready(unit: DeqDevice = Depends(get_device)) -> AudioStateRead:
    """Tells the unit this device is ready to play audio (0x1a).

    The real app sends it at the end of every cold start, right after the
    mode write, and the connect sequence here never has. The car went
    silent whenever the Pi attached, and this is the one frame of the
    app's opening conversation still missing, so it is here as a lever to
    hear what it does, not as a fix. It has no body and the reply is a
    status only.
    """
    return run_on_unit(
        lambda: unit.run(
            lambda session: (session.notify_play_ready(), _read_audio_state(session))[1]
        )
    )


@router.post("/audio-source", response_model=AudioStateRead)
def set_audio_source(
    body: AudioSourceWrite, unit: DeqDevice = Depends(get_device)
) -> AudioStateRead:
    """Picks which input the unit plays. THROUGH is the car's own audio."""
    if body.name not in AUDIO_SOURCE.names:
        raise HTTPException(status_code=422, detail=f"unknown audio source {body.name}")
    return run_on_unit(
        lambda: unit.run(
            lambda session: (
                session.set_audio_source(body.name),
                _read_audio_state(session),
            )[1]
        )
    )


# There is deliberately no mute endpoint.
#
# `SET_MUTE_STATE` (0x0f) is not honoured by a real unit: it answered
# SOUND_OFF with STATUS 0 and then reported SOUND_ON anyway, captured in
# `20261008_mute_state_reply.hex`, which is why `FakeDeq.accept_mute_state`
# keeps its own state unchanged. An endpoint built on it would acknowledge
# every request and change nothing, which is worse than not having one.
#
# Mute is still reported by `GET /device/audio`, because reading it is
# useful even when setting it is not. If muting ever needs to work from
# here, the untried candidates are SET_SPEAKER_MUTE_STATE (0x13) and
# SET_SYSTEM_MUTE_STATE (0x1b); both need a real unit to confirm.

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
    # The column stores the tuning as plain JSON, so validate it before
    # the DSP code reads it by attribute.
    tuning = TuningData.model_validate(profile.data)
    run_on_unit(lambda: unit.write_tuning(tuning))
    return DeviceRead(**vars(unit.state()))


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
    """Runs one action, turning an unreachable unit into a 503.

    A bad value name is the caller's mistake, so it answers 400 instead.

    Returns whatever the action returned. The existing callers write to
    the unit and then build their own reply from `unit.state()`, so they
    ignore it; the audio endpoints read from the unit and need it.
    """
    try:
        return action()
    except DeviceUnavailable as caught_error:
        raise HTTPException(
            status_code=DEVICE_UNAVAILABLE_STATUS, detail=str(caught_error)
        ) from caught_error
    except KeyError as caught_error:
        raise HTTPException(status_code=400, detail=str(caught_error)) from caught_error
