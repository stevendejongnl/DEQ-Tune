"""Checks the update endpoints against a temporary updater directory."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.test_updates import STATE, RecordingRunner
from app.updates import ReleaseUpdates, get_release_updates


@pytest.fixture
def directory(tmp_path):
    return tmp_path


@pytest.fixture
def runner():
    return RecordingRunner()


@pytest.fixture
def update_client(directory, runner):
    app.dependency_overrides[get_release_updates] = lambda: ReleaseUpdates(directory, run_command=runner)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_release_updates)


def test_reads_the_state(update_client, directory):
    (directory / "deq-update-state.json").write_text(json.dumps(STATE))

    body = update_client.get("/api/updates").json()

    assert body["supported"] is True
    assert body["latest"] == "1.17.0"
    assert body["history"] == [{"from_version": "0.0.0", "to_version": "1.16.0", "at": "2026-10-23T14:07:18+00:00"}]


def test_switches_automatic_updates_off(update_client, directory):
    (directory / "deq-update-state.json").write_text(json.dumps(STATE))

    body = update_client.put("/api/updates/settings", json={"automatic": False}).json()

    assert body["automatic"] is False


def test_asks_for_an_update(update_client, directory, runner):
    (directory / "deq-update-state.json").write_text(json.dumps(STATE))

    assert update_client.post("/api/updates/request").status_code == 202
    assert len(runner.commands) == 1


def test_a_machine_with_no_updater_refuses_a_write(update_client):
    assert update_client.get("/api/updates").json()["supported"] is False
    assert update_client.put("/api/updates/settings", json={"automatic": False}).status_code == 503
    assert update_client.post("/api/updates/request").status_code == 503
