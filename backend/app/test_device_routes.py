"""Checks the device endpoints against a DEQ that answers like the real one."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.deq_blob import BANK_B, SpeakerRecord, UserConfiguration
from app.deq_device import DeqDevice, format_firmware_version
from app.device_routes import _read_audio_state, get_device
from app.main import app
from app.active_profile import ActiveProfile
from app.active_profile_routes import get_active_profile
from sqlmodel import Session
from app.testing.fake_deq import FAKE_SERIAL, FakeDeq


@pytest.fixture
def unit() -> DeqDevice:
    """A device whose transport is a fake unit, injected through the seam."""
    return DeqDevice(build_transport_function=FakeDeq)


@pytest.fixture(name="device_client")
def device_client_fixture(seeded_client: TestClient, unit: DeqDevice, engine) -> TestClient:
    """The seeded client from `conftest`, with the fake unit injected too, and
    an active-profile keeper on the test database."""
    app.dependency_overrides[get_device] = lambda: unit
    keeper = ActiveProfile(unit, lambda: Session(engine))
    app.dependency_overrides[get_active_profile] = lambda: keeper
    yield seeded_client
    app.dependency_overrides.pop(get_device, None)
    app.dependency_overrides.pop(get_active_profile, None)


def test_the_unit_starts_disconnected(device_client: TestClient) -> None:
    body = device_client.get("/api/device").json()
    assert body["connected"] is False
    assert body["firmware_version"] is None


def test_connecting_reports_what_the_unit_says(device_client: TestClient) -> None:
    body = device_client.post("/api/device/connect").json()
    assert body["connected"] is True
    assert body["firmware_version"] == "2.02"
    assert body["serial"] == FAKE_SERIAL


def test_disconnecting_clears_the_state(device_client: TestClient) -> None:
    device_client.post("/api/device/connect")
    body = device_client.post("/api/device/disconnect").json()
    assert body["connected"] is False


def test_a_link_that_cannot_open_reports_the_reason(device_client: TestClient) -> None:
    """A unit that never answers is a normal state, so the reason comes back
    in the body rather than as a failed request."""
    app.dependency_overrides[get_device] = lambda: DeqDevice(
        build_transport_function=lambda: FakeDeq(answers=False)
    )
    body = device_client.post("/api/device/connect").json()
    assert body["connected"] is False
    assert "no reply" in body["problem"]


def test_the_options_come_from_the_pioneer_app(device_client: TestClient) -> None:
    body = device_client.get("/api/device/options").json()
    assert len(body["eq_styles"]) == 20
    assert len(body["live_simulations"]) == 7
    assert {"name": "SUPER_BASS", "wire_value": 3} in body["eq_styles"]
    assert {"name": "OPERA_HALL", "wire_value": 6} in body["live_simulations"]


def test_the_options_offer_only_the_named_audio_sources(device_client: TestClient) -> None:
    """`audio_source` carries no `string_id` for any value. The real app never
    puts it behind a labelled picker the way it does eq_style and
    live_simulation. So `AUDIO_SOURCE_CHOICES` in `schemas.py` picks the three
    with a plain meaning by name. The rest (`SP_OTHER_SOURCE`, the `MIX_*`
    pairs, `UNKNOWN`) are wire-internal states that `/volume` passes through on
    its own. A person should not pick them."""
    body = device_client.get("/api/device/options").json()
    names = [value["name"] for value in body["audio_sources"]]

    assert names == ["STAND_ALONE", "CAR_SOURCE", "THROUGH"]
    assert {"name": "THROUGH", "wire_value": 4} in body["audio_sources"]


def test_the_options_leave_out_the_unknown_sentinel(device_client: TestClient) -> None:
    """A decoder returns `UNKNOWN` for a wire value it does not recognise. It
    is no setting, and the real app never offers it. Its picker reads a label
    from the app's resources, and an entry with none never reaches the list.
    When this app offered it, the picker showed a tile with no label. A pick of
    it would write wire value 0."""
    body = device_client.get("/api/device/options").json()

    assert "UNKNOWN" not in [value["name"] for value in body["eq_styles"]]
    assert "UNKNOWN" not in [value["name"] for value in body["live_simulations"]]
    assert 0 not in [value["wire_value"] for value in body["eq_styles"]]
    assert 0 not in [value["wire_value"] for value in body["live_simulations"]]


def test_pushing_a_profile_sends_four_blocks(device_client: TestClient, unit: DeqDevice) -> None:
    device_client.post("/api/device/connect")
    profile_id = device_client.get("/api/profiles").json()[0]["id"]

    assert device_client.post(f"/api/device/tuning/{profile_id}").status_code == 200

    transport = unit.require_session().transport
    coefficient_writes = [one for one in transport.exchanges if one.request.command_id == 0x05]
    assert len(coefficient_writes) == 4


def test_pushing_a_profile_that_does_not_exist_is_a_404(device_client: TestClient) -> None:
    device_client.post("/api/device/connect")
    assert device_client.post("/api/device/tuning/999999").status_code == 404


def test_pushing_a_profile_with_no_unit_is_a_503(device_client: TestClient) -> None:
    """An unplugged unit is not a broken request, so it answers 503."""
    profile_id = device_client.get("/api/profiles").json()[0]["id"]
    assert device_client.post(f"/api/device/tuning/{profile_id}").status_code == 503


def test_selecting_an_eq_style_reaches_the_units_blob(
    device_client: TestClient, unit: DeqDevice
) -> None:
    """A style is a byte in the settings blob, not a command of its own."""
    device_client.post("/api/device/connect")
    assert device_client.post("/api/device/eq-style", json={"name": "SUPER_BASS"}).status_code == 200
    assert unit.require_session().transport.configuration.preset_index_a == 3


def test_selecting_a_live_simulation_reaches_the_units_blob(
    device_client: TestClient, unit: DeqDevice
) -> None:
    device_client.post("/api/device/connect")
    response = device_client.post("/api/device/live-simulation", json={"name": "OPERA_HALL"})
    assert response.status_code == 200
    assert unit.require_session().transport.configuration.sound_field == 6


def test_a_style_goes_to_the_bank_the_unit_plays(
    device_client: TestClient, unit: DeqDevice
) -> None:
    """The unit keeps two equalizer banks and plays the one `bank_in_use`
    names. Each has its own preset index. So a write of bank A's index while
    the unit plays bank B changes nothing a listener can hear.

    This app does not offer the banks as a choice. The Pioneer app shows them
    as "Custom A" and "Custom B", because it has nowhere else to keep a curve.
    Here a profile is a named curve, and a person can keep any number. The bank
    is only where a profile lands."""
    device_client.post("/api/device/connect")
    transport = unit.require_session().transport
    transport.configuration.bank_in_use = BANK_B

    assert device_client.post("/api/device/eq-style", json={"name": "SUPER_BASS"}).status_code == 200

    # A write replaces the fake's configuration, the way the unit stores a
    # new blob, so read it back rather than holding the old object.
    assert transport.configuration.preset_index_b == 3
    assert transport.configuration.preset_index_a == 0


def test_a_style_the_unit_does_not_have_is_a_400(device_client: TestClient) -> None:
    device_client.post("/api/device/connect")
    assert device_client.post("/api/device/eq-style", json={"name": "NOT_A_STYLE"}).status_code == 400


def test_the_firmware_version_reads_the_way_the_app_shows_it() -> None:
    """The captured accessory string says `2.02`, from the bytes `0x0202`."""
    assert format_firmware_version(0x0202) == "2.02"
    assert format_firmware_version(0x0310) == "3.16"


def test_the_audio_state_reports_what_the_unit_holds(
    device_client: TestClient,
) -> None:
    device_client.post("/api/device/connect")
    body = device_client.get("/api/device/audio").json()
    assert body["source_mode"] == "CAR_SOURCE"
    assert body["source_mode_wire"] == 3
    assert body["muted"] is False
    assert isinstance(body["volume_db"], int)


def test_a_mute_read_of_0_means_the_unit_plays() -> None:
    """A real unit answered the mute read with 0 on 2026-10-10. The field is
    a boolean, so 0 means it plays."""

    class Session:
        def read_mode(self) -> int:
            return 4

        def read_volume(self) -> int:
            return 0

        def read_mute_state(self) -> int:
            return 0

        def read_driving_state(self) -> int:
            return 0

    state = _read_audio_state(Session())

    assert state.mute_state_wire == 0
    assert state.muted is False
    assert state.source_mode == "THROUGH"


def test_setting_the_volume_puts_the_source_mode_back(
    device_client: TestClient,
) -> None:
    """The unit refuses a volume write while it holds THROUGH.

    So the endpoint moves to an OTHER mode, writes, and restores. A unit left
    on SP_OTHER_SOURCE would play whatever this device writes, which is
    silence. The endpoint exists to get people out of that failure.
    """
    device_client.post("/api/device/connect")
    device_client.post("/api/device/audio-source", json={"name": "THROUGH"})
    body = device_client.post("/api/device/volume", json={"volume_db": -20}).json()
    assert body["volume_db"] == -20
    assert body["source_mode"] == "THROUGH"


def test_play_ready_is_sent_and_the_audio_state_comes_back(
    device_client: TestClient,
) -> None:
    device_client.post("/api/device/connect")

    answer = device_client.post("/api/device/play-ready")

    assert answer.status_code == 200
    assert answer.json()["source_mode"] == "CAR_SOURCE"


def test_play_ready_without_a_unit_answers_503(device_client: TestClient) -> None:
    device_client.post("/api/device/disconnect")

    assert device_client.post("/api/device/play-ready").status_code == 503


def test_setting_the_volume_ends_with_play_ready_after_the_mode_comes_back(
    device_client: TestClient, unit: DeqDevice
) -> None:
    """A slider move cut the car's audio. The mode went to an OTHER mode and
    back, and a return to THROUGH alone leaves the car silent until PLAY_READY
    follows it."""
    device_client.post("/api/device/connect")
    device_client.post("/api/device/audio-source", json={"name": "THROUGH"})
    transport = unit.require_session().transport
    sent_before = len(transport.command_order)

    device_client.post("/api/device/volume", json={"volume_db": -20})

    sent = transport.command_order[sent_before:]
    # read mode, to OTHER, write volume, back to THROUGH, PLAY_READY, then the
    # four reads that build the reply.
    assert sent == [0x0C, 0x0B, 0x0D, 0x0B, 0x1A, 0x0C, 0x0E, 0x10, 0x11]


def test_a_volume_the_unit_takes_needs_no_mode_change(
    device_client: TestClient, unit: DeqDevice
) -> None:
    """A mode change cuts the audio for a moment. On CAR_SOURCE the route
    writes first, and a write that took needs nothing more."""
    device_client.post("/api/device/connect")
    transport = unit.require_session().transport
    sent_before = len(transport.command_order)

    body = device_client.post("/api/device/volume", json={"volume_db": -20}).json()

    sent = transport.command_order[sent_before:]
    # read mode, write volume, then the four reads of the reply.
    assert sent == [0x0C, 0x0D, 0x0C, 0x0E, 0x10, 0x11]
    assert body["volume_db"] == -20


def test_a_refused_volume_moves_the_mode_and_puts_it_back(
    device_client: TestClient, unit: DeqDevice
) -> None:
    """The unit refuses with STATUS -6. The route catches that, moves the
    mode and writes again, and the link stays up."""
    device_client.post("/api/device/connect")
    transport = unit.require_session().transport
    # Suppose CAR_SOURCE (3) refuses too, as THROUGH does.
    transport.volume_refused_in_modes = {3, 4}
    sent_before = len(transport.command_order)

    body = device_client.post("/api/device/volume", json={"volume_db": -20}).json()

    sent = transport.command_order[sent_before:]
    assert sent[:6] == [0x0C, 0x0D, 0x0B, 0x0D, 0x0B, 0x1A]
    assert unit.state().connected


def test_changing_the_audio_source_is_followed_by_play_ready(
    device_client: TestClient, unit: DeqDevice
) -> None:
    device_client.post("/api/device/connect")
    transport = unit.require_session().transport
    sent_before = len(transport.command_order)

    device_client.post("/api/device/audio-source", json={"name": "THROUGH"})

    sent = transport.command_order[sent_before:]
    assert sent[:2] == [0x0B, 0x1A]


def test_the_audio_source_can_be_changed_and_read_back(
    device_client: TestClient,
) -> None:
    device_client.post("/api/device/connect")
    body = device_client.post(
        "/api/device/audio-source", json={"name": "SP_OTHER_SOURCE"}
    ).json()
    assert body["source_mode"] == "SP_OTHER_SOURCE"
    assert body["source_mode_wire"] == 5


def test_an_unknown_audio_source_is_refused(device_client: TestClient) -> None:
    device_client.post("/api/device/connect")
    answer = device_client.post("/api/device/audio-source", json={"name": "NONSENSE"})
    assert answer.status_code == 422
    assert "NONSENSE" in answer.json()["detail"]


def test_the_units_tune_becomes_a_custom_profile(device_client: TestClient) -> None:
    configuration = UserConfiguration(speakers=[SpeakerRecord(level_db=-2.0)] * 7)
    app.dependency_overrides[get_device] = lambda: connected_device(configuration)

    response = device_client.post("/api/device/profile", json={"name": "Car tune"})

    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "custom"
    assert body["data"]["speakers"]["FL"]["levelDB"] == -2.0
    stored = device_client.get(f"/api/profiles/{body['id']}").json()
    assert stored["name"] == "Car tune"


def test_a_tune_this_app_cannot_read_is_a_409(device_client: TestClient) -> None:
    app.dependency_overrides[get_device] = lambda: connected_device(
        UserConfiguration(band_count=20)
    )

    response = device_client.post("/api/device/profile", json={"name": "Car tune"})

    assert response.status_code == 409


def test_saving_the_units_tune_needs_a_unit(device_client: TestClient) -> None:
    response = device_client.post("/api/device/profile", json={"name": "Car tune"})

    assert response.status_code == 503


def connected_device(configuration: UserConfiguration) -> DeqDevice:
    """Returns a connected device whose fake unit holds `configuration`."""
    device = DeqDevice(build_transport_function=lambda: FakeDeq(configuration=configuration))
    device.connect()
    return device


def test_a_chosen_audio_source_is_kept_for_the_next_link(device_client: TestClient) -> None:
    device_client.post("/api/device/connect")

    device_client.post("/api/device/audio-source", json={"name": "THROUGH"})

    assert device_client.get("/api/active-profile").json()["source_mode"] == "THROUGH"


def test_mute_and_unmute_write_the_boolean_and_report_it(
    device_client: TestClient, unit: DeqDevice
) -> None:
    """The wire carries 1 for muted and 0 for playing, as the app's `b/e/aa`
    writes it. The enum values 2 and 1 would make "unmute" mute."""
    device_client.post("/api/device/connect")

    muted = device_client.post("/api/device/mute", json={"muted": True}).json()
    playing = device_client.post("/api/device/mute", json={"muted": False}).json()

    assert (muted["muted"], muted["mute_state_wire"]) == (True, 1)
    assert (playing["muted"], playing["mute_state_wire"]) == (False, 0)


def test_mute_without_a_unit_answers_503(device_client: TestClient) -> None:
    device_client.post("/api/device/disconnect")

    assert device_client.post("/api/device/mute", json={"muted": True}).status_code == 503
