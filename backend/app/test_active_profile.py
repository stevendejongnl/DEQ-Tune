"""Checks that the active profile reaches the unit, now or on the next link."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session

from app.active_profile import ActiveProfile, read_active_profile_id
from app.deq_blob import BANK_A, BANK_B
from app.deq_device import DeqDevice
from app.deq_dsp import build_equalizer_payload
from app.deq_enums import EQ_STYLE
from app.deq_session import (
    COMMAND_SET_MODE,
    CONFIG_ID_EQUALIZER,
    cancelled_band_gains_db,
    selected_band_gains_db,
)
from app.eq_data import TuningData
from app.equalizers import with_equalizer
from app.models import Equalizer, Profile
from app.seed import load_preset
from app.testing.fake_deq import FakeDeq

COMMAND_WRITE_COEFFICIENTS = 0x05
PRESET = next(
    (Path(__file__).resolve().parents[2] / "data" / "presets" / "mazda").glob(
        "tuning_preset_*.json"
    )
)


class FakeUnits:
    """Builds one FakeDeq per link and keeps each, so a test can read what
    every link was sent."""

    def __init__(self) -> None:
        self.links: list[FakeDeq] = []

    def build(self) -> FakeDeq:
        self.links.append(FakeDeq())
        return self.links[-1]

    def pushes_on_last_link(self) -> int:
        return sum(
            1
            for exchange in self.links[-1].exchanges
            if exchange.request.command_id == COMMAND_WRITE_COEFFICIENTS
        )


@pytest.fixture(name="units")
def units_fixture() -> FakeUnits:
    return FakeUnits()


@pytest.fixture(name="unit")
def unit_fixture(units: FakeUnits) -> DeqDevice:
    return DeqDevice(build_transport_function=units.build)


@pytest.fixture(name="keeper")
def keeper_fixture(engine, unit: DeqDevice) -> ActiveProfile:
    keeper = ActiveProfile(unit, lambda: Session(engine))
    unit.after_connect = keeper.apply_after_connect
    unit.source_for_connect = keeper.source_for_connect
    return keeper


def store_profile(engine, data: dict | None = None) -> int:
    with Session(engine) as session:
        profile = load_preset(PRESET)
        profile.source = "custom"
        if data is not None:
            profile.data = data
        session.add(profile)
        session.commit()
        return profile.id


def test_no_active_profile_says_none(keeper: ActiveProfile):
    state = keeper.state()

    assert state.profile_id is None
    assert state.status == "none"


def test_a_profile_activated_offline_waits_for_the_unit(engine, keeper, units):
    profile_id = store_profile(engine)

    state = keeper.activate(profile_id)

    assert state.status == "waiting"
    assert units.links == []
    with Session(engine) as session:
        assert read_active_profile_id(session) == profile_id


def test_the_unit_gets_the_active_profile_when_it_connects(engine, keeper, unit, units):
    profile_id = store_profile(engine)
    keeper.activate(profile_id)

    unit.connect()

    assert units.pushes_on_last_link() == 3
    assert keeper.state().status == "applied"


def test_a_profile_activated_while_connected_goes_on_at_once(engine, keeper, unit, units):
    unit.connect()
    profile_id = store_profile(engine)

    state = keeper.activate(profile_id)

    assert state.status == "applied"
    assert units.pushes_on_last_link() == 3


def test_every_new_link_gets_the_profile_again(engine, keeper, unit, units):
    """A unit that lost power has lost the coefficients too."""
    keeper.activate(store_profile(engine))
    unit.connect()

    unit.connect()

    assert len(units.links) == 2
    assert units.pushes_on_last_link() == 3
    assert keeper.state().status == "applied"


def test_an_edit_after_the_push_makes_the_unit_outdated(engine, keeper, unit):
    unit.connect()
    profile_id = store_profile(engine)
    keeper.activate(profile_id)

    with Session(engine) as session:
        profile = session.get(Profile, profile_id)
        edited = dict(profile.data)
        edited["faderBalance"] = {"fader": 3.0, "balance": 0.0}
        profile.data = edited
        session.add(profile)
        session.commit()

    assert keeper.state().status == "outdated"
    assert keeper.activate(profile_id).status == "applied"


def test_a_failed_push_says_why_and_keeps_the_choice(engine, keeper, unit):
    unit.connect()
    broken = load_preset(PRESET).data
    broken["foundationEq"]["eqs"]["LR"]["selectedBank"] = 9
    profile_id = store_profile(engine, broken)

    state = keeper.activate(profile_id)

    assert state.status == "failed"
    assert "selects bank 9" in state.problem
    assert state.profile_id == profile_id


def test_a_failed_push_on_connect_keeps_the_link(engine, keeper, unit):
    broken = load_preset(PRESET).data
    broken["foundationEq"]["eqs"]["LR"]["selectedBank"] = 9
    keeper.activate(store_profile(engine, broken))

    assert unit.connect().connected
    assert keeper.state().status == "failed"


def test_activating_a_missing_profile_raises(keeper: ActiveProfile):
    with pytest.raises(LookupError):
        keeper.activate(999999)


def store_equalizer(engine, gains: list[float]) -> int:
    with Session(engine) as session:
        equalizer = Equalizer(name="Style", source="custom", gains=gains)
        session.add(equalizer)
        session.commit()
        return equalizer.id


def last_equalizer_payload(units: FakeUnits) -> bytes:
    writes = [
        exchange.request.body
        for exchange in units.links[-1].exchanges
        if exchange.request.command_id == COMMAND_WRITE_COEFFICIENTS
        and int.from_bytes(exchange.request.body[:4], "little") == CONFIG_ID_EQUALIZER
    ]
    return writes[-1][4:]


def test_the_unit_gets_the_profile_plus_the_eq(engine, keeper, unit, units):
    unit.connect()
    profile_id = store_profile(engine)
    style = [3.0] * 13
    keeper.activate(profile_id)

    state = keeper.activate_equalizer(store_equalizer(engine, style))

    assert state.status == "applied"
    tuning = with_equalizer(TuningData.model_validate(load_preset(PRESET).data), style)
    plain = selected_band_gains_db(tuning)
    expected = build_equalizer_payload(cancelled_band_gains_db(tuning, plain), plain)
    assert last_equalizer_payload(units) == expected


def test_an_eq_chosen_offline_goes_on_with_the_profile(engine, keeper, unit, units):
    keeper.activate(store_profile(engine))
    keeper.activate_equalizer(store_equalizer(engine, [2.0] * 13))

    unit.connect()

    assert keeper.state().status == "applied"
    assert keeper.state().equalizer_id is not None


def test_an_edited_eq_makes_the_unit_outdated(engine, keeper, unit):
    unit.connect()
    keeper.activate(store_profile(engine))
    equalizer_id = store_equalizer(engine, [2.0] * 13)
    keeper.activate_equalizer(equalizer_id)

    with Session(engine) as session:
        equalizer = session.get(Equalizer, equalizer_id)
        equalizer.gains = [4.0] * 13
        session.add(equalizer)
        session.commit()

    assert keeper.state().status == "outdated"


def test_a_push_puts_the_units_style_on_custom_a(engine, keeper, unit, units):
    unit.connect()
    units.links[-1].configuration.bank_in_use = BANK_B

    keeper.activate(store_profile(engine))

    configuration = units.links[-1].configuration
    assert configuration.bank_in_use == BANK_A
    assert configuration.preset_index_a == EQ_STYLE.by_name("CUSTOM").wire_value


def test_activating_a_missing_eq_raises(keeper: ActiveProfile):
    with pytest.raises(LookupError):
        keeper.activate_equalizer(999999)


def test_the_remembered_source_mode_is_set_on_connect(keeper, unit, units):
    keeper.remember_source("THROUGH")

    unit.connect()

    mode_writes = [
        exchange.request.body
        for exchange in units.links[-1].exchanges
        if exchange.request.command_id == COMMAND_SET_MODE
    ]
    assert int.from_bytes(mode_writes[0], "little", signed=True) == 4


def test_with_nothing_remembered_a_link_starts_on_car_source(keeper):
    assert keeper.source_for_connect() == "CAR_SOURCE"


def test_a_source_chosen_while_connected_goes_on_at_once(keeper, unit, units):
    unit.connect()

    state = keeper.choose_source("THROUGH")

    assert state.source_mode == "THROUGH"
    assert units.links[-1].mode == 4
