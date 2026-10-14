"""Checks how the backend talks to the Wi-Fi helper."""

from __future__ import annotations

import subprocess

import pytest

from app.testing.fake_wifi_helper import FakeWifiHelper
from app.wifi_networks import (
    HELPER_COMMAND,
    SavedNetwork,
    VisibleNetwork,
    WifiNetworks,
    WifiRefused,
    WifiUnavailable,
)


def test_reads_the_saved_and_the_visible_networks():
    helper = FakeWifiHelper(
        saved={"CloudSuite": True},
        visible=[{"ssid": "CloudSuite", "signal": 79, "secured": True}],
    )
    networks = WifiNetworks(run_command=helper)

    assert networks.saved() == [SavedNetwork(ssid="CloudSuite", connected=True)]
    assert networks.visible() == [VisibleNetwork(ssid="CloudSuite", signal=79, secured=True)]


def test_a_password_goes_on_stdin_and_never_on_the_command_line():
    commands: list[list[str]] = []
    helper = FakeWifiHelper()

    def recording_helper(command, **options):
        commands.append(command)
        return helper(command, **options)

    WifiNetworks(run_command=recording_helper).save("Home", "secret-password")

    assert commands == [[*HELPER_COMMAND, "save", "Home"]]
    assert helper.passwords == ["secret-password"]


def test_a_refusal_carries_the_helpers_reason():
    helper = FakeWifiHelper(saved={"Home": True}, deq_session_running=True)

    with pytest.raises(WifiRefused, match="DEQ is connected"):
        WifiNetworks(run_command=helper).forget("Home")


def test_a_machine_with_no_helper_cannot_manage_wifi():
    def missing_sudo(command, **options):
        raise FileNotFoundError("sudo")

    with pytest.raises(WifiUnavailable):
        WifiNetworks(run_command=missing_sudo).saved()


def test_sudo_with_no_rule_for_the_helper_cannot_manage_wifi():
    def sudo_asks_for_a_password(command, **options):
        return subprocess.CompletedProcess(command, 1, "", "sudo: a password is required")

    with pytest.raises(WifiUnavailable, match="password is required"):
        WifiNetworks(run_command=sudo_asks_for_a_password).saved()
