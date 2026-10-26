#!/usr/bin/env python3
"""Installs each new deq-tune release on the Pi by itself.

`deq-updater.timer` runs this program every 30 minutes, as root. One run:

1. It asks GitHub for the latest release. The Pi has internet only on a
   client Wi-Fi network, so a run in the car finds no route and stops.
2. It writes what it found to the state file. The web app reads that file
   to show "a new version exists" and the changelog note.
3. When automatic updates are on and the release is newer, it downloads
   the release tarball, checks its SHA-256, and unpacks it into a staging
   tree. It runs `uv sync` there, as the user `deq`, while the Pi still
   has internet. That fills uv's cache and proves that every dependency
   resolves.
4. It swaps the staging tree in and keeps the running tree as the
   rollback copy. Then it builds `.venv` again in the live tree, offline,
   from uv's cache. A virtualenv records its own absolute path in its
   scripts, so the one built in staging fails after the rename: the
   backend then failed with "Failed to spawn: uvicorn" on 2026-10-23.
   It restarts the backend and waits for `/health`. A backend that does
   not answer gets the rollback copy back.
5. It updates the gadget only while no DEQ session is live. A restart of
   the gadget ends the session. The DEQ starts a new one within a second
   (measured 2026-10-26), but the car's sound breaks for that moment. A
   backend restart keeps the session, because the gadget keeps the link
   until the backend returns. So a gadget change can wait for a later run,
   and the state file says so.
6. Right after it installed a release, it installs the programs that run
   from /usr/local/bin when that release changed them: the BLE bridge, its
   pairing rules, and this updater. A run with no new release leaves them
   alone, so a program deployed by hand stays until the next release. It
   keeps the old copy as `.prev`. It updates only programs that the Pi
   has, so a Pi without the bridge gets no bridge. It restarts the bridge
   at once, also during a DEQ session: that drops the phone's Bluetooth
   link for a few seconds and does not touch the DEQ. A new updater runs
   from the next timer run on.

The person can switch automatic updates off in the settings file. Then a
run still checks and writes the state, and an update happens only when
the request file exists. The web app writes that file for its Update
button.

The program uses the standard library only, because it must run before
any `uv sync`.
"""

from __future__ import annotations

import datetime
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

REPOSITORY = "stevendejongnl/deq-tune"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"

HOME = Path("/home/deq")
LIVE_TREE = HOME / "deq-tune"
PREVIOUS_TREE = HOME / "deq-tune.prev"
STAGING_TREE = HOME / "deq-tune.next"
INSTALLED_GADGET = HOME / "deq_accessory.py"
SETTINGS_PATH = HOME / "deq-update-settings.json"
REQUEST_PATH = HOME / "deq-update-request"
STATE_PATH = HOME / "deq-update-state.json"
GADGET_SOCKET = Path("/run/deq-accessory.sock")
UV = HOME / ".local" / "bin" / "uv"

BACKEND_SERVICE = "deq-backend"
GADGET_SERVICE = "deq-accessory"
HEALTH_URL = "http://127.0.0.1:8420/health"

# The tarball unpacks into one top directory of this name.
TARBALL_ROOT = "deq-tune"
VERSION_FILE = "VERSION"
GADGET_IN_TREE = Path("pi-gadget") / "deq_accessory.py"

# The programs that run from /usr/local/bin, and the service that runs
# each one. The updater has no service: its timer starts it again.
PROGRAMS_DIRECTORY = Path("/usr/local/bin")
PROGRAMS_IN_TREE = Path("pi-gadget")
PROGRAMS = {
    "deq_ble_bridge.py": "deq-ble-bridge",
    "deq_ble_pairing.py": "deq-ble-bridge",
    "deq_updater.py": None,
}

NETWORK_TIMEOUT_SECONDS = 20
HEALTH_WAIT_SECONDS = 60
# A version the Pi reports when its tree has no VERSION file. That is a tree
# from before the updater, so any release counts as newer.
UNKNOWN_VERSION = "0.0.0"


class UpdateError(Exception):
    """An update step failed. The live tree is unchanged or restored."""


def parse_version(text: str) -> tuple[int, ...]:
    """Returns `1.15.0` or `v1.15.0` as a tuple that compares in order."""
    cleaned = text.strip().removeprefix("v")
    return tuple(int(part) for part in cleaned.split("."))


def is_newer(candidate: str, installed: str) -> bool:
    return parse_version(candidate) > parse_version(installed)


def read_installed_version(tree: Path) -> str:
    version_path = tree / VERSION_FILE
    if not version_path.exists():
        return UNKNOWN_VERSION
    return version_path.read_text().strip()


def automatic_updates_on(settings_path: Path) -> bool:
    """Automatic updates are on unless the settings file says otherwise."""
    if not settings_path.exists():
        return True
    try:
        return bool(json.loads(settings_path.read_text()).get("automatic", True))
    except (json.JSONDecodeError, AttributeError):
        return True


@dataclass(frozen=True)
class Release:
    """The parts of a GitHub release that an update needs."""

    version: str
    tarball_url: str
    checksum_url: str
    notes: str
    page_url: str


def release_from_github(payload: dict) -> Release:
    """Picks the tarball and its checksum out of the release's assets."""
    version = payload["tag_name"].removeprefix("v")
    tarball_name = f"deq-tune-{version}.tar.gz"
    assets = {asset["name"]: asset["browser_download_url"] for asset in payload.get("assets", [])}
    if tarball_name not in assets or f"{tarball_name}.sha256" not in assets:
        raise UpdateError(f"release {version} has no {tarball_name} with its checksum")
    return Release(
        version=version,
        tarball_url=assets[tarball_name],
        checksum_url=assets[f"{tarball_name}.sha256"],
        notes=payload.get("body") or "",
        page_url=payload.get("html_url") or "",
    )


def check_sha256(data: bytes, checksum_text: str) -> None:
    """Raises unless the data has the checksum. The file is `sha256sum` output."""
    expected = checksum_text.split()[0].lower()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise UpdateError(f"checksum mismatch: expected {expected}, got {actual}")


def unpack_tarball(data: bytes, destination: Path) -> None:
    """Unpacks the release into `destination`, and refuses any unsafe member.

    Every member must sit under the tarball's top directory. A member with an
    absolute path, a `..` part, or a link is refused, so a damaged or hostile
    tarball cannot write outside the staging tree.
    """
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            parts = Path(member.name).parts
            if member.name.startswith("/") or ".." in parts or parts[:1] != (TARBALL_ROOT,):
                raise UpdateError(f"unsafe path in tarball: {member.name}")
            if member.issym() or member.islnk():
                raise UpdateError(f"link in tarball: {member.name}")
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True)
        for member in members:
            relative = Path(*Path(member.name).parts[1:])
            if relative == Path("."):
                continue
            target = destination / relative
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                continue
            target.write_bytes(source.read())
            target.chmod(member.mode & 0o755)


def swap_trees(staging: Path, live: Path, previous: Path) -> None:
    """Makes the staging tree live, and keeps the live tree as the rollback copy."""
    if previous.exists():
        shutil.rmtree(previous)
    if live.exists():
        live.rename(previous)
    staging.rename(live)


def restore_previous(live: Path, previous: Path) -> None:
    """Puts the rollback copy back. The failed tree is deleted."""
    if not previous.exists():
        raise UpdateError("no rollback copy to restore")
    if live.exists():
        shutil.rmtree(live)
    previous.rename(live)


def gadget_differs(tree: Path, installed_gadget: Path) -> bool:
    candidate = tree / GADGET_IN_TREE
    if not candidate.exists():
        return False
    if not installed_gadget.exists():
        return True
    return candidate.read_bytes() != installed_gadget.read_bytes()


def changed_programs(tree: Path, programs_directory: Path) -> list[str]:
    """The programs to install from `tree`: changed, and in a group the Pi has.

    A group is the programs that one service runs. The Pi has a group when
    it has any program of it, so a new file joins a group the Pi runs.
    """
    groups_on_pi = {
        service for name, service in PROGRAMS.items() if (programs_directory / name).exists()
    }
    changed = []
    for name, service in PROGRAMS.items():
        candidate = tree / PROGRAMS_IN_TREE / name
        target = programs_directory / name
        if not candidate.exists() or service not in groups_on_pi:
            continue
        if target.exists() and target.read_bytes() == candidate.read_bytes():
            continue
        changed.append(name)
    return changed


def install_program(candidate: Path, target: Path) -> None:
    """Replaces `target` in one step and keeps the old copy as `.prev`."""
    if target.exists():
        shutil.copy2(target, target.with_name(target.name + ".prev"))
    staged = target.with_name(target.name + ".new")
    shutil.copy2(candidate, staged)
    os.chmod(staged, 0o755)
    staged.replace(target)


@dataclass
class State:
    """What the web app reads to show versions and the changelog note."""

    installed: str
    latest: str | None = None
    automatic: bool = True
    update_available: bool = False
    gadget_pending: bool = False
    notes: str = ""
    release_url: str = ""
    checked_at: str = ""
    last_result: str = ""
    history: list[dict] = field(default_factory=list)


class System:
    """The real Pi: network, services and files. A test passes a fake instead."""

    def fetch_json(self, url: str) -> dict:
        request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
            return json.loads(response.read())

    def download(self, url: str) -> bytes:
        with urllib.request.urlopen(url, timeout=NETWORK_TIMEOUT_SECONDS * 6) as response:
            return response.read()

    def sync_dependencies(self, tree: Path, offline: bool = False) -> None:
        """Builds `backend/.venv` as the user deq. Offline uses uv's cache only."""
        subprocess.run(["chown", "-R", "deq:deq", str(tree)], check=True)
        shutil.rmtree(tree / "backend" / ".venv", ignore_errors=True)
        command = ["runuser", "-u", "deq", "--", str(UV), "sync", "--frozen"]
        if offline:
            command.append("--offline")
        subprocess.run(command, cwd=tree / "backend", check=True)

    def restart(self, service: str) -> None:
        subprocess.run(["systemctl", "restart", service], check=True)

    def backend_healthy(self) -> bool:
        deadline = time.monotonic() + HEALTH_WAIT_SECONDS
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(HEALTH_URL, timeout=3) as response:
                    if response.status == 200:
                        return True
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(2)
        return False

    def session_live(self) -> bool:
        return GADGET_SOCKET.exists()

    def install_gadget(self, tree: Path) -> None:
        shutil.copy2(tree / GADGET_IN_TREE, INSTALLED_GADGET)
        self.restart(GADGET_SERVICE)

    def now(self) -> str:
        return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


@dataclass
class Paths:
    live: Path = LIVE_TREE
    previous: Path = PREVIOUS_TREE
    staging: Path = STAGING_TREE
    installed_gadget: Path = INSTALLED_GADGET
    programs: Path = PROGRAMS_DIRECTORY
    settings: Path = SETTINGS_PATH
    request: Path = REQUEST_PATH
    state: Path = STATE_PATH


class Updater:
    """Runs one update check. It depends on a `System` and on `Paths`."""

    def __init__(self, system: System, paths: Paths) -> None:
        self.system = system
        self.paths = paths

    def run_once(self) -> State:
        state = self.read_state()
        state.installed = read_installed_version(self.paths.live)
        state.automatic = automatic_updates_on(self.paths.settings)
        state.checked_at = self.system.now()
        try:
            release = release_from_github(self.system.fetch_json(LATEST_RELEASE_URL))
        except (urllib.error.URLError, OSError, KeyError, UpdateError) as caught_error:
            state.last_result = f"no release check: {caught_error}"
            self.finish_gadget(state)
            return self.write_state(state)

        state.latest = release.version
        state.notes = release.notes
        state.release_url = release.page_url
        state.update_available = is_newer(release.version, state.installed)
        asked = self.paths.request.exists()
        if state.update_available and (state.automatic or asked):
            self.install(release, state)
        elif not state.update_available:
            state.last_result = f"up to date at {state.installed}"
        else:
            state.last_result = f"{release.version} waits for the Update button"
        if asked:
            self.paths.request.unlink(missing_ok=True)
        self.finish_gadget(state)
        return self.write_state(state)

    def install(self, release: Release, state: State) -> None:
        try:
            data = self.system.download(release.tarball_url)
            check_sha256(data, self.system.download(release.checksum_url).decode())
            unpack_tarball(data, self.paths.staging)
            self.system.sync_dependencies(self.paths.staging)
        except (UpdateError, urllib.error.URLError, OSError, subprocess.CalledProcessError) as caught_error:
            shutil.rmtree(self.paths.staging, ignore_errors=True)
            state.last_result = f"download of {release.version} failed: {caught_error}"
            return
        from_version = state.installed
        swap_trees(self.paths.staging, self.paths.live, self.paths.previous)
        try:
            self.system.sync_dependencies(self.paths.live, offline=True)
            started = True
        except (OSError, subprocess.CalledProcessError):
            started = False
        if started:
            self.system.restart(BACKEND_SERVICE)
            started = self.system.backend_healthy()
        if not started:
            restore_previous(self.paths.live, self.paths.previous)
            self.system.restart(BACKEND_SERVICE)
            state.last_result = f"{release.version} did not start, so {from_version} is back"
            return
        state.installed = release.version
        state.update_available = False
        state.last_result = f"updated from {from_version} to {release.version}"
        state.history.insert(0, {"from": from_version, "to": release.version, "at": state.checked_at})
        del state.history[10:]
        self.install_programs(state)

    def finish_gadget(self, state: State) -> None:
        """Installs a changed gadget, but never during a live DEQ session."""
        if not gadget_differs(self.paths.live, self.paths.installed_gadget):
            state.gadget_pending = False
            return
        if self.system.session_live():
            state.gadget_pending = True
            return
        self.system.install_gadget(self.paths.live)
        state.gadget_pending = False

    def install_programs(self, state: State) -> None:
        """Installs the new release's changed programs and restarts their services.

        Only right after a release went in. A run with no new release leaves
        the programs alone, because the tree can then be older than a program
        that someone deployed by hand, and a compare would put the old one back.
        """
        changed = changed_programs(self.paths.live, self.paths.programs)
        if not changed:
            return
        services: list[str] = []
        for name in changed:
            install_program(self.paths.live / PROGRAMS_IN_TREE / name, self.paths.programs / name)
            service = PROGRAMS[name]
            if service is not None and service not in services:
                services.append(service)
        state.last_result += f"; installed {', '.join(changed)}"
        for service in services:
            try:
                self.system.restart(service)
            except (OSError, subprocess.CalledProcessError) as caught_error:
                state.last_result += f"; {service} did not restart: {caught_error}"

    def read_state(self) -> State:
        if not self.paths.state.exists():
            return State(installed=UNKNOWN_VERSION)
        try:
            return State(**json.loads(self.paths.state.read_text()))
        except (json.JSONDecodeError, TypeError):
            return State(installed=UNKNOWN_VERSION)

    def write_state(self, state: State) -> State:
        temporary = self.paths.state.with_suffix(".tmp")
        temporary.write_text(json.dumps(state.__dict__, indent=2))
        os.chmod(temporary, 0o644)
        temporary.replace(self.paths.state)
        return state


def main() -> int:
    state = Updater(System(), Paths()).run_once()
    print(state.last_result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
