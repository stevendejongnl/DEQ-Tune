"""Checks the updater's files as the app reads and writes them."""

from __future__ import annotations

import json

from app.updates import START_UPDATER, ReleaseUpdates

STATE = {
    "installed": "1.16.0",
    "latest": "1.17.0",
    "automatic": True,
    "update_available": True,
    "gadget_pending": False,
    "notes": "### Features\n- a settings page",
    "release_url": "https://github.com/example/releases/v1.17.0",
    "checked_at": "2026-10-23T14:00:00+00:00",
    "last_result": "1.17.0 waits for the Update button",
    "history": [{"from": "0.0.0", "to": "1.16.0", "at": "2026-10-23T14:07:18+00:00"}],
}


class RecordingRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str]) -> int:
        self.commands.append(command)
        return 0


def test_a_machine_with_no_updater_says_so(tmp_path):
    assert not ReleaseUpdates(tmp_path).read().supported


def test_the_state_file_reaches_the_app(tmp_path):
    (tmp_path / "deq-update-state.json").write_text(json.dumps(STATE))

    status = ReleaseUpdates(tmp_path).read()

    assert status.supported
    assert (status.installed, status.latest, status.update_available) == ("1.16.0", "1.17.0", True)
    assert status.history[0].from_version == "0.0.0"
    assert status.history[0].to_version == "1.16.0"


def test_the_settings_file_wins_over_the_last_run(tmp_path):
    (tmp_path / "deq-update-state.json").write_text(json.dumps(STATE))
    updates = ReleaseUpdates(tmp_path)

    status = updates.set_automatic(False)

    assert not status.automatic
    assert json.loads((tmp_path / "deq-update-settings.json").read_text()) == {"automatic": False}


def test_a_request_writes_the_file_and_starts_the_updater(tmp_path):
    runner = RecordingRunner()

    ReleaseUpdates(tmp_path, run_command=runner).request_update()

    assert (tmp_path / "deq-update-request").exists()
    assert runner.commands == [START_UPDATER]
