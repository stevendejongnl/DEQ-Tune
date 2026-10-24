"""Checks the Wi-Fi helper's keyfile edits, which need no NetworkManager."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deq_wifi_networks import (  # noqa: E402
    REBOOT_DELAY_SECONDS,
    Refusal,
    keyfile_with_key,
    restart_for_new_key,
    set_access_point_key,
)

ACCESS_POINT_KEYFILE = """[connection]
id=deq-tune-ap
type=wifi

[wifi]
mode=ap
ssid=deq-tune

[wifi-security]
key-mgmt=wpa-psk
psk=deq-tune-bridge

[ipv4]
method=shared
"""


def test_the_new_key_replaces_only_the_psk_line() -> None:
    text = keyfile_with_key(ACCESS_POINT_KEYFILE, "a new key")
    assert "psk=a\\snew\\skey\n" in text
    assert "deq-tune-bridge" not in text
    assert text.replace("psk=a\\snew\\skey", "psk=deq-tune-bridge") == ACCESS_POINT_KEYFILE


def test_a_key_with_a_backslash_does_not_read_as_an_escape() -> None:
    text = keyfile_with_key(ACCESS_POINT_KEYFILE, r"key\1\g<0>x")
    assert "psk=key\\\\1\\\\g<0>x\n" in text


def test_a_keyfile_without_a_psk_line_is_refused() -> None:
    with pytest.raises(Refusal):
        keyfile_with_key(ACCESS_POINT_KEYFILE.replace("psk=deq-tune-bridge\n", ""), "a new key")


@pytest.mark.parametrize("key", ["", "short", "x" * 64, "tab\there"])
def test_a_bad_key_is_refused_before_any_file_changes(key: str) -> None:
    with pytest.raises(Refusal):
        set_access_point_key(key)


class RecordingRunner:
    """Records each command instead of running it."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, command, **_options) -> None:
        self.commands.append(command)


def test_a_new_key_restarts_the_pi_after_a_delay() -> None:
    runner = RecordingRunner()

    restart_for_new_key(run_command=runner)

    assert runner.commands == [["systemd-run", f"--on-active={REBOOT_DELAY_SECONDS}", "systemctl", "reboot"]]
