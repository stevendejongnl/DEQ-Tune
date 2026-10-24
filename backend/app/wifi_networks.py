"""The Wi-Fi networks that the bridge joins.

At home the Pi joins a client network on `wlan0`, beside its own access
point. A person adds a network from the app, so nobody has to log in to the
Pi and run `nmcli`.

The backend runs as an ordinary user, and NetworkManager needs root to save
a connection. So this module runs one helper, `deq-wifi-networks`, through
`sudo`. The sudoers rule names that helper and nothing else, and the helper
checks every argument again. This module never builds an `nmcli` command.

A machine with no helper, such as a laptop or CI, answers that it cannot
manage Wi-Fi. It does not fail the rest of the app.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

HELPER_PATH = "/usr/local/bin/deq-wifi-networks"
HELPER_COMMAND = ("sudo", "-n", HELPER_PATH)
HELPER_TIMEOUT_SECONDS = 30.0

# The helper exits with this code when it refuses a request. Its stderr then
# says why, in words for a person.
REFUSAL_EXIT_CODE = 2


class WifiUnavailable(Exception):
    """This machine cannot manage Wi-Fi. The message is for a person."""


class WifiRefused(Exception):
    """The helper refused a request. The message is for a person."""


@dataclass(frozen=True)
class SavedNetwork:
    ssid: str
    # True while the bridge uses this network.
    connected: bool


@dataclass(frozen=True)
class VisibleNetwork:
    ssid: str
    # 0 to 100, as NetworkManager reports it.
    signal: int
    secured: bool


@dataclass(frozen=True)
class AccessPoint:
    ssid: str
    # True while the key is still the public default of configure-access-point.sh.
    uses_default_key: bool


class WifiNetworks:
    """Lists, saves and forgets the networks that the bridge joins.

    A route calls its methods. It depends on a command runner with the shape
    of `subprocess.run`, which a test replaces with a fake helper.
    """

    def __init__(self, run_command=subprocess.run, helper_command=HELPER_COMMAND) -> None:
        self.run_command = run_command
        self.helper_command = tuple(helper_command)

    def saved(self) -> list[SavedNetwork]:
        return [SavedNetwork(**network) for network in self.run_helper("saved")]

    def visible(self) -> list[VisibleNetwork]:
        return [VisibleNetwork(**network) for network in self.run_helper("visible")]

    def save(self, ssid: str, password: str) -> list[SavedNetwork]:
        """Saves a network, or replaces the saved one with the same name.

        The password goes to the helper on stdin, so it never shows in a
        process list.
        """
        saved = self.run_helper("save", ssid, input_text=password + "\n")
        return [SavedNetwork(**network) for network in saved]

    def forget(self, ssid: str) -> list[SavedNetwork]:
        return [SavedNetwork(**network) for network in self.run_helper("forget", ssid)]

    def request_join(self) -> None:
        """Asks the bridge to join a saved network in range now, and not
        at the next timer run. The join itself happens after this returns."""
        self.run_helper("join")

    def access_point(self) -> AccessPoint | None:
        """The Pi's own access point, or None when the Pi has none."""
        read = self.run_helper("access-point")
        return None if read is None else AccessPoint(**read)

    def set_access_point_key(self, key: str) -> AccessPoint | None:
        """Saves a new access point key. The helper also restarts the Pi a few
        seconds later, so the key applies.

        The key goes on stdin, as a network's password does.
        """
        read = self.run_helper("access-point-key", input_text=key + "\n")
        return None if read is None else AccessPoint(**read)

    def run_helper(self, *arguments: str, input_text: str = "") -> object:
        try:
            completed = self.run_command(
                [*self.helper_command, *arguments],
                input=input_text,
                capture_output=True,
                text=True,
                timeout=HELPER_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as caught_error:
            raise WifiUnavailable(f"the Wi-Fi helper did not run: {caught_error}") from caught_error
        message = (completed.stderr or "").strip()
        if completed.returncode == REFUSAL_EXIT_CODE:
            raise WifiRefused(message)
        if completed.returncode != 0:
            # sudo with no rule for the helper, or no helper at all, ends up
            # here. So does an nmcli failure inside the helper.
            raise WifiUnavailable(message or f"the Wi-Fi helper exited with {completed.returncode}")
        return json.loads(completed.stdout)


wifi_networks = WifiNetworks()


def get_wifi_networks() -> WifiNetworks:
    """The route dependency. A test overrides it with a fake helper."""
    return wifi_networks
