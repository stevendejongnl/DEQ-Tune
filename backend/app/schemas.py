from __future__ import annotations

from pydantic import BaseModel

from app.deq_enums import AUDIO_SOURCE, EQ_STYLE, LIVE_SIMULATION
from app.eq_data import TuningData


class ProfileRead(BaseModel):
    id: int
    name: str
    source: str
    brand_name: str | None
    car_model: str | None
    speaker_type: str | None
    supported_processors: list[str]
    data: TuningData


class ProfileCreate(BaseModel):
    name: str
    data: TuningData
    brand_name: str | None = None
    car_model: str | None = None
    speaker_type: str | None = None
    supported_processors: list[str] = []


class ProfileUpdate(BaseModel):
    name: str | None = None
    data: TuningData | None = None


class DeviceRead(BaseModel):
    """What the header shows about the unit."""

    connected: bool
    firmware_version: str | None = None
    serial: str | None = None
    problem: str | None = None


class AudioStateRead(BaseModel):
    """What the unit is actually doing with sound, read live from it.

    Deliberately separate from `DeviceRead`. That one is polled by the
    header and never opens a link; every field here costs a request and a
    reply over USB, so asking for them is a choice the caller makes.

    This exists because a tuning can apply perfectly and still produce
    silence, and until now nothing said so: on 2026-10-09 profiles and EQ
    styles were applied in a car with no sound at all, and there was no
    way to see whether the unit was muted, near the bottom of its volume
    range, or holding a source that plays nothing.
    """

    source_mode: str
    source_mode_wire: int
    volume_db: int
    muted: bool
    # What the unit actually said. `muted` is true only for SOUND_OFF (2); a
    # real unit has answered 0, which is neither state the app declares.
    mute_state_wire: int
    driving: bool


class VolumeWrite(BaseModel):
    volume_db: int


class AudioSourceWrite(BaseModel):
    name: str


class BridgeNoticeRead(BaseModel):
    """One fault the bridge has seen since it started."""

    key: str
    severity: str
    message: str
    first_seen_seconds: float
    last_seen_seconds: float
    count: int


class BridgeRead(BaseModel):
    """What the app shows about the machine holding the link.

    This is the bridge, not the DEQ. The two fail for different reasons
    and ask different things of a person: a DEQ that is off is normal,
    and a bridge that is browning out is a fault in the wiring.

    The undervoltage fields are `None` where the machine cannot tell. A
    laptop has no `vcgencmd`, and `False` would be a claim it cannot
    make.
    """

    undervoltage_now: bool | None = None
    undervoltage_since_boot: bool | None = None
    uptime_seconds: float | None = None
    notices: list[BridgeNoticeRead] = []


class DeqEnumValueRead(BaseModel):
    """One value the unit accepts, as the Pioneer app declares it."""

    name: str
    wire_value: int


class DeviceOptionsRead(BaseModel):
    """Every value set the unit's own DSP offers.

    These come from the app, through `deq_enums.json`, so the frontend
    never has to keep a list of its own.
    """

    eq_styles: list[DeqEnumValueRead]
    live_simulations: list[DeqEnumValueRead]
    audio_sources: list[DeqEnumValueRead]


class EqStyleWrite(BaseModel):
    """Which built-in EQ style to select on the unit."""

    name: str


class LiveSimulationWrite(BaseModel):
    """Which built-in live-simulation mode to select on the unit."""

    name: str


#: The audio-source values worth offering as a pick. `audio_source` carries
#: no `string_id` for any value in `deq_enums.json` -- unlike eq_style and
#: live_simulation, the decompiled app never puts this behind a labelled
#: picker, it reaches the processor tab some other way. These three are the
#: ones with a plain meaning: THROUGH is the car's own audio and the default
#: (see `DEFAULT_AUDIO_SOURCE`), CAR_SOURCE and STAND_ALONE are the unit's
#: other named modes. The rest (`SP_OTHER_SOURCE`, the `MIX_*` pairs,
#: `UNKNOWN`) are wire-internal states `/volume` passes through on its own,
#: not something a person should pick.
AUDIO_SOURCE_CHOICES = ("STAND_ALONE", "CAR_SOURCE", "THROUGH")


def device_options() -> DeviceOptionsRead:
    """Returns the choices the unit offers, read from the app's own enums.

    These are the `selectable` values, not every value. `UNKNOWN` is what
    a decoder returns for a wire value it does not recognise, so offering
    it put a tile with no label in the picker, and choosing it would have
    written wire value 0.
    """
    return DeviceOptionsRead(
        eq_styles=[
            DeqEnumValueRead(name=value.name, wire_value=value.wire_value)
            for value in EQ_STYLE.selectable
        ],
        live_simulations=[
            DeqEnumValueRead(name=value.name, wire_value=value.wire_value)
            for value in LIVE_SIMULATION.selectable
        ],
        audio_sources=[
            DeqEnumValueRead(name=value.name, wire_value=value.wire_value)
            for value in AUDIO_SOURCE
            if value.name in AUDIO_SOURCE_CHOICES
        ],
    )
