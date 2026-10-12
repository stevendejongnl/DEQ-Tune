"""Checks the device endpoints against a DEQ that answers like the real one."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.deq_blob import BANK_B
from app.deq_device import DeqDevice, format_firmware_version
from app.device_routes import _read_audio_state, get_device
from app.main import app
from app.testing.fake_deq import FAKE_SERIAL, FakeDeq


@pytest.fixture
def unit() -> DeqDevice:
    """A device whose transport is a fake unit, injected through the seam."""
    return DeqDevice(build_transport_function=FakeDeq)


@pytest.fixture(name="device_client")
def device_client_fixture(seeded_client: TestClient, unit: DeqDevice) -> TestClient:
    """The seeded client from `conftest`, with the fake unit injected too."""
    app.dependency_overrides[get_device] = lambda: unit
    yield seeded_client
    app.dependency_overrides.pop(get_device, None)


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
    """`audio_source` carries no `string_id` for any value -- the real app
    never puts it behind a labelled picker the way it does eq_style and
    live_simulation. `AUDIO_SOURCE_CHOICES` in `schemas.py` picks the three
    with a plain meaning by name instead; the rest (`SP_OTHER_SOURCE`, the
    `MIX_*` pairs, `UNKNOWN`) are wire-internal states `/volume` passes
    through on its own, not something a person should pick."""
    body = device_client.get("/api/device/options").json()
    names = [value["name"] for value in body["audio_sources"]]

    assert names == ["STAND_ALONE", "CAR_SOURCE", "THROUGH"]
    assert {"name": "THROUGH", "wire_value": 4} in body["audio_sources"]


def test_the_options_leave_out_the_unknown_sentinel(device_client: TestClient) -> None:
    """`UNKNOWN` is what a decoder returns for a wire value it does not
    recognise. It is not a setting, and the real app never offers it: its
    picker reads a label from the app's resources, and an entry with none
    never reaches the list. Offering it here put a tile with no label in
    the picker, and choosing it would have written wire value 0."""
    body = device_client.get("/api/device/options").json()

    assert "UNKNOWN" not in [value["name"] for value in body["eq_styles"]]
    assert "UNKNOWN" not in [value["name"] for value in body["live_simulations"]]
    assert 0 not in [value["wire_value"] for value in body["eq_styles"]]
    assert 0 not in [value["wire_value"] for value in body["live_simulations"]]


def test_pushing_a_profile_sends_three_blocks(device_client: TestClient, unit: DeqDevice) -> None:
    device_client.post("/api/device/connect")
    profile_id = device_client.get("/api/profiles").json()[0]["id"]

    assert device_client.post(f"/api/device/tuning/{profile_id}").status_code == 200

    transport = unit.require_session().transport
    coefficient_writes = [one for one in transport.exchanges if one.request.command_id == 0x05]
    assert len(coefficient_writes) == 3


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
    names. Each has its own preset index, so writing bank A's index while
    the unit plays bank B changes nothing a listener can hear.

    The banks are not a choice this app offers. The Pioneer app shows them
    as "Custom A" and "Custom B" because it has nowhere else to keep a
    curve; here a profile is a named curve and there can be any number.
    The bank is only where a profile lands."""
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
    assert body["source_mode"] == "THROUGH"
    assert body["source_mode_wire"] == 4
    assert body["muted"] is False
    assert isinstance(body["volume_db"], int)


def test_a_mute_value_the_app_does_not_declare_does_not_fail_the_read() -> None:
    """A real unit answered the mute read with 0 on 2026-10-10. The enum
    holds only -1, 1 and 2, and the lookup used to raise, which failed the
    whole read and left the panel blank."""

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

    So the endpoint moves to an OTHER mode, writes, and restores. Leaving
    it on SP_OTHER_SOURCE would play whatever this device writes, which is
    silence -- the failure the endpoint exists to get people out of.
    """
    device_client.post("/api/device/connect")
    body = device_client.post("/api/device/volume", json={"volume_db": -20}).json()
    assert body["volume_db"] == -20
    assert body["source_mode"] == "THROUGH"


def test_play_ready_is_sent_and_the_audio_state_comes_back(
    device_client: TestClient,
) -> None:
    device_client.post("/api/device/connect")

    answer = device_client.post("/api/device/play-ready")

    assert answer.status_code == 200
    assert answer.json()["source_mode"] == "THROUGH"


def test_play_ready_without_a_unit_answers_503(device_client: TestClient) -> None:
    device_client.post("/api/device/disconnect")

    assert device_client.post("/api/device/play-ready").status_code == 503


def test_setting_the_volume_ends_with_play_ready_after_the_mode_comes_back(
    device_client: TestClient, unit: DeqDevice
) -> None:
    """Moving the slider cut the car's audio: the mode went to an OTHER
    mode and back, and returning to THROUGH alone leaves the car silent
    until PLAY_READY follows it."""
    device_client.post("/api/device/connect")
    transport = unit.require_session().transport
    sent_before = len(transport.command_order)

    device_client.post("/api/device/volume", json={"volume_db": -20})

    sent = transport.command_order[sent_before:]
    # read mode, to OTHER, write volume, back to THROUGH, PLAY_READY, then the
    # four reads that build the reply.
    assert sent == [0x0C, 0x0B, 0x0D, 0x0B, 0x1A, 0x0C, 0x0E, 0x10, 0x11]


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
