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
    """What the unit does with sound, read live from it.

    A separate model from `DeviceRead`, on purpose. The header polls that one,
    and it never opens a link. Every field here costs a request and a reply
    over USB. So the caller chooses when to ask for them.

    This model exists because a tuning can apply without error and still give
    silence, and nothing said so before. On 2026-10-09 a person applied
    profiles and EQ styles in a car with no sound at all. The app could not
    show whether the unit was on mute, near the bottom of its volume range, or
    on a source that plays nothing.
    """

    source_mode: str
    source_mode_wire: int
    volume_db: int
    muted: bool
    # What the unit said. `muted` is true only for SOUND_OFF (2). A real unit
    # answered 0 once, which is neither state that the app declares.
    mute_state_wire: int
    driving: bool


class VolumeWrite(BaseModel):
    volume_db: int


class AudioSourceWrite(BaseModel):
    name: str


class BridgeNoticeRead(BaseModel):
    """One fault that the bridge saw since it started."""

    key: str
    severity: str
    message: str
    first_seen_seconds: float
    last_seen_seconds: float
    count: int


class BridgeRead(BaseModel):
    """What the app shows about the machine that holds the link.

    This model describes the bridge, and not the DEQ. The two fail for
    different reasons and ask different things of a person. A DEQ that is off
    is normal. A bridge that browns out has a fault in the wiring.

    The undervoltage fields are `None` where the machine cannot tell. A laptop
    has no `vcgencmd`, and `False` would be a claim it cannot make.
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


#: The audio-source values worth offering as a pick. `audio_source` carries no
#: `string_id` for any value in `deq_enums.json`. That differs from eq_style
#: and live_simulation. The decompiled app never puts this enum behind a
#: labelled picker. It reaches the processor tab some other way.
#:
#: These three have a plain meaning. THROUGH is the car's own audio and the
#: default (see `DEFAULT_AUDIO_SOURCE`). CAR_SOURCE and STAND_ALONE are the
#: unit's other named modes. The rest (`SP_OTHER_SOURCE`, the `MIX_*` pairs,
#: `UNKNOWN`) are wire-internal states that `/volume` passes through on its
#: own. A person should not pick them.
AUDIO_SOURCE_CHOICES = ("STAND_ALONE", "CAR_SOURCE", "THROUGH")


def device_options() -> DeviceOptionsRead:
    """Returns the choices the unit offers, read from the app's own enums.

    These are the `selectable` values, and not every value. A decoder returns
    `UNKNOWN` for a wire value it does not recognise. When the app offered it,
    the picker showed a tile with no label. A pick of it would write wire value
    0.
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
