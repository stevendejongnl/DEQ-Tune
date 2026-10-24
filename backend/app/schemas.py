from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

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
    favorite: bool
    data: TuningData


class ProfileCreate(BaseModel):
    name: str
    data: TuningData
    brand_name: str | None = None
    car_model: str | None = None
    speaker_type: str | None = None
    supported_processors: list[str] = []


class UnitProfileCreate(BaseModel):
    """The name for a profile read from the unit."""

    name: str


class ActiveProfileRead(BaseModel):
    """What the unit should play, and whether it plays it now.

    `profile_id` is the car profile and `equalizer_id` the EQ on top of it.
    `status` is one of none, waiting, applied, outdated and failed, for the
    two together. `problem` says why the last push failed. `source_mode` is
    the mode that each new link gets.
    """

    profile_id: int | None
    status: str
    problem: str | None = None
    equalizer_id: int | None = None
    source_mode: str


class ActiveProfileWrite(BaseModel):
    profile_id: int


class ActiveSourceWrite(BaseModel):
    """A name from the AUDIO_SOURCE enum."""

    name: str


class ActiveEqualizerWrite(BaseModel):
    """`None` plays the car profile with no EQ on top."""

    equalizer_id: int | None


EQUALIZER_GAIN_COUNT = 13
EQUALIZER_GAIN_LIMIT_DB = 12.0


class EqualizerRead(BaseModel):
    id: int
    name: str
    source: str
    favorite: bool
    gains: list[float]


class EqualizerGains(BaseModel):
    """Checks a curve: 13 gains, each within ±12 dB."""

    gains: list[float] = Field(
        min_length=EQUALIZER_GAIN_COUNT, max_length=EQUALIZER_GAIN_COUNT
    )

    @field_validator("gains")
    @classmethod
    def gains_in_range(cls, gains: list[float]) -> list[float]:
        for gain in gains:
            if abs(gain) > EQUALIZER_GAIN_LIMIT_DB:
                raise ValueError(f"a gain of {gain} dB is outside ±12 dB")
        return gains


class EqualizerCreate(EqualizerGains):
    name: str


class EqualizerUpdate(BaseModel):
    name: str | None = None
    gains: list[float] | None = Field(
        default=None, min_length=EQUALIZER_GAIN_COUNT, max_length=EQUALIZER_GAIN_COUNT
    )

    @field_validator("gains")
    @classmethod
    def gains_in_range(cls, gains: list[float] | None) -> list[float] | None:
        return gains if gains is None else EqualizerGains.gains_in_range(gains)


class FavoriteWrite(BaseModel):
    favorite: bool


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
    # What the unit said: 1 muted, 0 playing. The wire carries a boolean, and
    # not the MUTE_STATE enum.
    mute_state_wire: int
    driving: bool


class VolumeWrite(BaseModel):
    volume_db: int


class MuteWrite(BaseModel):
    muted: bool


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


class NetworkInterfaceRead(BaseModel):
    """One network interface of the bridge, without loopback."""

    name: str
    state: str
    mac_address: str | None = None
    addresses: list[str] = []
    received_bytes: int | None = None
    sent_bytes: int | None = None
    # Only a wireless interface has a signal.
    signal_dbm: float | None = None


class BridgeSystemRead(BaseModel):
    """The bridge's machine statistics, for the app's system dialog.

    Each field is `None` where the machine cannot tell. A laptop has no Pi
    model and no `vcgencmd`. `frontend_build` is the build id of the frontend
    that the bridge serves now. The app compares it with its own build id, and
    so tells a cached page from the current one.
    """

    hostname: str | None = None
    model: str | None = None
    operating_system: str | None = None
    kernel: str | None = None
    architecture: str | None = None
    python_version: str | None = None
    uptime_seconds: float | None = None
    load_average: list[float] | None = None
    cpu_count: int | None = None
    cpu_temperature_celsius: float | None = None
    cpu_frequency_mhz: float | None = None
    throttled_flags: str | None = None
    memory_total_bytes: int | None = None
    memory_available_bytes: int | None = None
    swap_total_bytes: int | None = None
    swap_free_bytes: int | None = None
    backend_memory_bytes: int | None = None
    disk_total_bytes: int | None = None
    disk_free_bytes: int | None = None
    frontend_build: str | None = None
    interfaces: list[NetworkInterfaceRead] = []


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
#: These three have a plain meaning. CAR_SOURCE is the car's own audio
#: through the unit's DSP, and the default (see `DEFAULT_AUDIO_SOURCE`).
#: THROUGH is the car's own audio, most likely past the DSP. STAND_ALONE is
#: the unit's other named mode. The rest (`SP_OTHER_SOURCE`, the `MIX_*` pairs,
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


WIFI_SSID_MAXIMUM_BYTES = 32


class SavedWifiNetworkRead(BaseModel):
    ssid: str
    # True while the bridge uses this network.
    connected: bool


class VisibleWifiNetworkRead(BaseModel):
    ssid: str
    # 0 to 100, as NetworkManager reports it.
    signal: int
    secured: bool


class WifiRead(BaseModel):
    """The networks that the bridge joins, and the networks in range.

    `visible` comes from the bridge's last scan. Nothing scans for this
    request, because a scan touches the radio.
    """

    saved: list[SavedWifiNetworkRead]
    visible: list[VisibleWifiNetworkRead]


class WifiNetworkWrite(BaseModel):
    """A network to save. An empty password saves an open network.

    The helper on the bridge checks the same rules again. This check gives
    the app a 422 before anything runs as root.
    """

    ssid: str
    password: str = ""

    @field_validator("ssid")
    @classmethod
    def ssid_fits(cls, ssid: str) -> str:
        if not 1 <= len(ssid.encode()) <= WIFI_SSID_MAXIMUM_BYTES:
            raise ValueError(f"a network name has 1 to {WIFI_SSID_MAXIMUM_BYTES} bytes")
        if any(ord(character) < 0x20 or ord(character) == 0x7F for character in ssid):
            raise ValueError("a network name cannot hold control characters")
        return ssid

    @field_validator("password")
    @classmethod
    def password_fits(cls, password: str) -> str:
        return password if password == "" else check_wifi_password(password)


def check_wifi_password(password: str) -> str:
    """WPA2's rules: 8 to 63 printable ASCII characters, or 64 hex digits."""
    is_hex_key = len(password) == 64 and all(character in "0123456789abcdefABCDEF" for character in password)
    if is_hex_key:
        return password
    if not 8 <= len(password) <= 63:
        raise ValueError("a Wi-Fi password has 8 to 63 characters")
    if any(not 0x20 <= ord(character) <= 0x7E for character in password):
        raise ValueError("a Wi-Fi password holds printable ASCII characters only")
    return password


class WifiForgetWrite(BaseModel):
    ssid: str


class AccessPointRead(BaseModel):
    """The Pi's own access point. It never carries the key: anyone in
    Bluetooth range can read this."""

    ssid: str
    # True while the key is still the public default, so the app asks the
    # person to change it.
    uses_default_key: bool


class AccessPointKeyWrite(BaseModel):
    """A new key for the access point. It applies at the access point's
    next start, which is the Pi's next boot."""

    key: str

    @field_validator("key")
    @classmethod
    def key_fits(cls, key: str) -> str:
        return check_wifi_password(key)


class UpdateHistoryRead(BaseModel):
    from_version: str
    to_version: str
    at: str


class UpdatesRead(BaseModel):
    """What the Pi's release updater last found.

    `supported` is false on a machine with no updater, such as a laptop.
    Then every other field keeps its default.
    """

    supported: bool
    installed: str | None = None
    latest: str | None = None
    automatic: bool = True
    update_available: bool = False
    gadget_pending: bool = False
    notes: str = ""
    release_url: str = ""
    checked_at: str = ""
    last_result: str = ""
    history: list[UpdateHistoryRead] = []
    # The build id of the web app that the bridge serves now. A page with
    # another id is an older copy, and reloads.
    frontend_build: str | None = None


class UpdateSettingsWrite(BaseModel):
    automatic: bool


class FrontendBundleRead(BaseModel):
    """The web app that the bridge serves, as a base64 zip in parts.

    `sha256` is the hash of the whole zip, after the parts are joined and
    decoded.
    """

    build: str
    sha256: str
    file_count: int
    part_count: int


class FrontendPartRead(BaseModel):
    build: str
    index: int
    data: str


LIBRARY_FORMAT = "deq-tune-library"
LIBRARY_FORMAT_VERSION = 1


class LibraryProfile(BaseModel):
    """A custom profile in an export. It has no id: the importing database
    gives it a new one."""

    name: str
    brand_name: str | None = None
    car_model: str | None = None
    speaker_type: str | None = None
    supported_processors: list[str] = []
    favorite: bool = False
    data: TuningData


class LibraryEqualizer(EqualizerGains):
    name: str
    favorite: bool = False


class LibraryExport(BaseModel):
    """A person's own library, as one file: the custom profiles, the custom
    EQs, and the stars on factory presets. The factory presets themselves
    come with every install, so the file names them only by their name."""

    format: str = LIBRARY_FORMAT
    version: int = LIBRARY_FORMAT_VERSION
    profiles: list[LibraryProfile] = []
    equalizers: list[LibraryEqualizer] = []
    starred_factory_profiles: list[str] = []
    starred_factory_equalizers: list[str] = []

    @field_validator("format")
    @classmethod
    def is_a_library(cls, format_name: str) -> str:
        if format_name != LIBRARY_FORMAT:
            raise ValueError(f"this is not a {LIBRARY_FORMAT} file")
        return format_name

    @field_validator("version")
    @classmethod
    def is_a_known_version(cls, version: int) -> int:
        if version > LIBRARY_FORMAT_VERSION:
            raise ValueError(f"this file has version {version}; update the app to read it")
        return version


class LibraryImportRead(BaseModel):
    """What an import added. An item that the library holds already, with
    the same name and the same content, counts as skipped."""

    profiles_added: int
    equalizers_added: int
    skipped: int
    stars_added: int
