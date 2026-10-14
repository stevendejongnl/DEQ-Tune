"""Checks how an EQ goes on top of the car profile, and the EQ routes."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.deq_session import selected_band_gains_db
from app.eq_data import TuningData
from app.equalizers import FACTORY_EQUALIZERS, combine_curves, seed_factory_equalizers, with_equalizer
from app.models import Equalizer
from app.seed import load_preset

PRESET = next(
    (Path(__file__).resolve().parents[2] / "data" / "presets" / "mazda").glob(
        "tuning_preset_*.json"
    )
)


def test_the_curves_add_band_for_band():
    assert combine_curves([1.0, -2.0, 0.0], [2.0, 1.5, -3.0]) == [3.0, -0.5, -3.0]


def test_the_sum_stays_inside_twelve_db_as_the_app_clamps_it():
    """The app clamps each term and then the sum (`service/f.a`)."""
    assert combine_curves([10.0, -14.0], [5.0, 3.0]) == [12.0, -9.0]


def test_with_equalizer_puts_the_sum_in_the_selected_bank():
    tuning = load_tuning()
    car = selected_band_gains_db(tuning)
    style = [1.0] * 13

    result = with_equalizer(tuning, style)

    assert selected_band_gains_db(result) == combine_curves(car, style)
    assert selected_band_gains_db(tuning) == car


def test_with_equalizer_converts_a_31_band_bank_first():
    tuning = load_tuning()
    slot = tuning.foundationEq.eqs["LR"]
    slot.banks[slot.selectedBank] = [0.0] * 31

    result = with_equalizer(tuning, [2.0] * 13)

    assert selected_band_gains_db(result) == [2.0] * 13


def test_the_seed_adds_each_factory_eq_once(session: Session):
    assert seed_factory_equalizers(session) == len(FACTORY_EQUALIZERS)
    assert seed_factory_equalizers(session) == 0
    flat = session.exec(select(Equalizer).where(Equalizer.name == "Flat")).one()
    assert flat.source == "factory"
    assert flat.gains == [0.0] * 13


def test_a_custom_eq_is_created_edited_and_deleted(client: TestClient):
    created = client.post("/api/equalizers", json={"name": "Mine", "gains": [1.0] * 13})
    assert created.status_code == 201
    equalizer_id = created.json()["id"]

    edited = client.put(f"/api/equalizers/{equalizer_id}", json={"gains": [2.0] * 13})
    assert edited.json()["gains"] == [2.0] * 13

    assert client.delete(f"/api/equalizers/{equalizer_id}").status_code == 204
    assert client.get("/api/equalizers").json() == []


def test_an_eq_needs_thirteen_gains_within_twelve_db(client: TestClient):
    assert client.post("/api/equalizers", json={"name": "Short", "gains": [0.0] * 12}).status_code == 422
    too_loud = [0.0] * 12 + [12.5]
    assert client.post("/api/equalizers", json={"name": "Loud", "gains": too_loud}).status_code == 422


def test_a_factory_eq_is_read_only_but_can_be_copied(client: TestClient, session: Session):
    seed_factory_equalizers(session)
    flat_id = client.get("/api/equalizers").json()[0]["id"]

    assert client.put(f"/api/equalizers/{flat_id}", json={"name": "Mine"}).status_code == 409
    assert client.delete(f"/api/equalizers/{flat_id}").status_code == 409
    copy = client.post(f"/api/equalizers/{flat_id}/duplicate").json()
    assert copy["source"] == "custom"
    assert copy["name"].endswith("(copy)")


def load_tuning() -> TuningData:
    return TuningData.model_validate(load_preset(PRESET).data)


def test_every_factory_eq_is_a_valid_curve():
    for name, gains in FACTORY_EQUALIZERS.items():
        assert len(gains) == 13, name
        assert all(abs(gain) <= 12 for gain in gains), name
