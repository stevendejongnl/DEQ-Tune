"""Checks the Pi updater against a fake system and real temporary trees."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import deq_updater  # noqa: E402
from deq_updater import (  # noqa: E402
    Paths,
    UpdateError,
    Updater,
    automatic_updates_on,
    check_sha256,
    is_newer,
    release_from_github,
    unpack_tarball,
)

NEW_VERSION = "1.16.0"
OLD_VERSION = "1.15.0"
NEW_GADGET = b"# gadget, new\n"
OLD_GADGET = b"# gadget, old\n"


def build_tarball(version: str, gadget: bytes = NEW_GADGET, extra: dict[str, bytes] | None = None) -> bytes:
    files = {
        "deq-tune/VERSION": f"{version}\n".encode(),
        "deq-tune/backend/app/main.py": b"# backend\n",
        "deq-tune/pi-gadget/deq_accessory.py": gadget,
    }
    files.update(extra or {})
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def github_release(version: str) -> dict:
    name = f"deq-tune-{version}.tar.gz"
    return {
        "tag_name": f"v{version}",
        "body": "### Features\n- something new",
        "html_url": f"https://github.com/example/releases/v{version}",
        "assets": [
            {"name": name, "browser_download_url": f"https://downloads/{name}"},
            {"name": f"{name}.sha256", "browser_download_url": f"https://downloads/{name}.sha256"},
        ],
    }


class FakeSystem:
    """A Pi that serves one release and records what the updater did."""

    def __init__(self, release: dict | None, tarball: bytes, healthy: bool = True, session_live: bool = False):
        self.release = release
        self.tarball = tarball
        self.healthy = healthy
        self.live_session = session_live
        self.restarts: list[str] = []
        self.synced: list[Path] = []
        self.gadget_installs: list[bytes] = []
        self.installed_gadget: Path | None = None

    def fetch_json(self, url: str) -> dict:
        if self.release is None:
            raise OSError("no route to host")
        return self.release

    def download(self, url: str) -> bytes:
        if url.endswith(".sha256"):
            return f"{hashlib.sha256(self.tarball).hexdigest()}  deq-tune.tar.gz\n".encode()
        return self.tarball

    def sync_dependencies(self, tree: Path) -> None:
        self.synced.append(tree)

    def restart(self, service: str) -> None:
        self.restarts.append(service)

    def backend_healthy(self) -> bool:
        return self.healthy

    def session_live(self) -> bool:
        return self.live_session

    def install_gadget(self, tree: Path) -> None:
        content = (tree / "pi-gadget" / "deq_accessory.py").read_bytes()
        self.gadget_installs.append(content)
        assert self.installed_gadget is not None
        self.installed_gadget.write_bytes(content)

    def now(self) -> str:
        return "2026-10-23T12:00:00+00:00"


@pytest.fixture(name="paths")
def paths_fixture(tmp_path: Path) -> Paths:
    live = tmp_path / "deq-tune"
    (live / "backend").mkdir(parents=True)
    (live / "VERSION").write_text(f"{OLD_VERSION}\n")
    (live / "pi-gadget").mkdir()
    (live / "pi-gadget" / "deq_accessory.py").write_bytes(OLD_GADGET)
    installed_gadget = tmp_path / "deq_accessory.py"
    installed_gadget.write_bytes(OLD_GADGET)
    return Paths(
        live=live,
        previous=tmp_path / "deq-tune.prev",
        staging=tmp_path / "deq-tune.next",
        installed_gadget=installed_gadget,
        settings=tmp_path / "settings.json",
        request=tmp_path / "request",
        state=tmp_path / "state.json",
    )


def make_updater(system: FakeSystem, paths: Paths) -> Updater:
    system.installed_gadget = paths.installed_gadget
    return Updater(system, paths)


def test_versions_compare_as_numbers():
    assert is_newer("1.16.0", "1.15.9")
    assert is_newer("v1.10.0", "1.9.3")
    assert not is_newer("1.15.0", "1.15.0")


def test_automatic_updates_stay_on_without_a_settings_file(tmp_path):
    assert automatic_updates_on(tmp_path / "missing.json")
    (tmp_path / "off.json").write_text(json.dumps({"automatic": False}))
    assert not automatic_updates_on(tmp_path / "off.json")


def test_a_release_without_the_tarball_is_refused():
    release = github_release(NEW_VERSION)
    release["assets"] = release["assets"][:1]
    with pytest.raises(UpdateError, match="checksum"):
        release_from_github(release)


def test_a_wrong_checksum_is_refused():
    with pytest.raises(UpdateError, match="mismatch"):
        check_sha256(b"data", "0" * 64)


@pytest.mark.parametrize("bad_name", ["/etc/passwd", "deq-tune/../escape", "other/file"])
def test_unpack_refuses_a_member_outside_the_tree(tmp_path, bad_name):
    tarball = build_tarball(NEW_VERSION, extra={bad_name: b"x"})
    with pytest.raises(UpdateError, match="unsafe"):
        unpack_tarball(tarball, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_an_automatic_update_swaps_the_trees_and_restarts_the_backend(paths):
    system = FakeSystem(github_release(NEW_VERSION), build_tarball(NEW_VERSION))

    state = make_updater(system, paths).run_once()

    assert (paths.live / "VERSION").read_text().strip() == NEW_VERSION
    assert (paths.previous / "VERSION").read_text().strip() == OLD_VERSION
    assert system.synced == [paths.staging]
    assert system.restarts[0] == "deq-backend"
    assert state.installed == NEW_VERSION
    assert state.history[0] == {"from": OLD_VERSION, "to": NEW_VERSION, "at": system.now()}
    assert json.loads(paths.state.read_text())["installed"] == NEW_VERSION


def test_a_backend_that_does_not_start_gets_the_old_tree_back(paths):
    system = FakeSystem(github_release(NEW_VERSION), build_tarball(NEW_VERSION), healthy=False)

    state = make_updater(system, paths).run_once()

    assert (paths.live / "VERSION").read_text().strip() == OLD_VERSION
    assert system.restarts == ["deq-backend", "deq-backend"]
    assert state.installed == OLD_VERSION
    assert "did not start" in state.last_result


def test_the_gadget_waits_while_a_session_is_live(paths):
    system = FakeSystem(github_release(NEW_VERSION), build_tarball(NEW_VERSION), session_live=True)

    state = make_updater(system, paths).run_once()

    assert system.gadget_installs == []
    assert paths.installed_gadget.read_bytes() == OLD_GADGET
    assert state.gadget_pending


def test_a_pending_gadget_goes_in_on_a_later_run_with_no_session(paths):
    system = FakeSystem(github_release(NEW_VERSION), build_tarball(NEW_VERSION), session_live=True)
    make_updater(system, paths).run_once()

    system.live_session = False
    state = make_updater(system, paths).run_once()

    assert system.gadget_installs == [NEW_GADGET]
    assert not state.gadget_pending


def test_opted_out_it_only_reports_the_new_version(paths):
    paths.settings.write_text(json.dumps({"automatic": False}))
    system = FakeSystem(github_release(NEW_VERSION), build_tarball(NEW_VERSION))

    state = make_updater(system, paths).run_once()

    assert state.update_available
    assert state.latest == NEW_VERSION
    assert (paths.live / "VERSION").read_text().strip() == OLD_VERSION
    assert system.restarts == []


def test_opted_out_the_update_button_installs_once(paths):
    paths.settings.write_text(json.dumps({"automatic": False}))
    paths.request.write_text("")
    system = FakeSystem(github_release(NEW_VERSION), build_tarball(NEW_VERSION))

    state = make_updater(system, paths).run_once()

    assert state.installed == NEW_VERSION
    assert not paths.request.exists()


def test_no_internet_keeps_everything_and_says_why(paths):
    system = FakeSystem(None, b"")

    state = make_updater(system, paths).run_once()

    assert state.installed == OLD_VERSION
    assert "no release check" in state.last_result
    assert system.restarts == []


def test_a_tree_from_before_the_updater_counts_as_old(paths):
    (paths.live / "VERSION").unlink()
    assert deq_updater.read_installed_version(paths.live) == deq_updater.UNKNOWN_VERSION
