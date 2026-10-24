"""A fake `deq-wifi-networks` helper, with the shape of `subprocess.run`.

Its JSON matches what the real helper printed on the Pi on 2026-10-14:

    saved    [{"ssid": "CloudSuite", "connected": true}, ...]
    visible  [{"ssid": "CloudSuite", "signal": 79, "secured": true}]

and what `access-point` printed there on 2026-10-23:

    {"ssid": "deq-tune", "uses_default_key": true}

The real helper never prints the access point's key, so neither does this.

It refuses as the real helper does: exit code 2, and the reason on stderr.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field


@dataclass
class FakeWifiHelper:
    # ssid -> connected
    saved: dict[str, bool] = field(default_factory=dict)
    visible: list[dict[str, object]] = field(default_factory=list)
    deq_session_running: bool = False
    # What each `save` read on stdin, in order.
    passwords: list[str] = field(default_factory=list)
    join_requests: int = 0
    # The access point's SSID and key, or None for a Pi without one.
    access_point: dict[str, str] | None = None

    def __call__(self, command, input="", **_options) -> subprocess.CompletedProcess:
        verb, *arguments = command[3:]
        try:
            output = self.answer(verb, arguments, input)
        except PermissionError as refusal:
            return subprocess.CompletedProcess(command, 2, "", str(refusal))
        return subprocess.CompletedProcess(command, 0, json.dumps(output), "")

    def answer(self, verb: str, arguments: list[str], stdin_text: str) -> object:
        if verb == "saved":
            return self.saved_list()
        if verb == "visible":
            return self.visible
        if verb == "save":
            self.passwords.append(stdin_text.rstrip("\n"))
            self.saved[arguments[0]] = False
            return self.saved_list()
        if verb == "forget":
            if arguments[0] not in self.saved:
                raise PermissionError(f"The Pi has no saved network named {arguments[0]}.")
            if self.saved[arguments[0]] and self.deq_session_running:
                raise PermissionError("The DEQ is connected, so the Pi cannot leave the network it uses now.")
            del self.saved[arguments[0]]
            return self.saved_list()
        if verb == "join":
            if self.deq_session_running:
                raise PermissionError("The DEQ is connected, so the Pi cannot join a network now.")
            self.join_requests += 1
            return None
        if verb == "access-point":
            return self.access_point_read()
        if verb == "access-point-key":
            if self.access_point is None:
                raise PermissionError("The Pi has no access point. Run configure-access-point.sh first.")
            self.access_point["key"] = stdin_text.rstrip("\n")
            return self.access_point_read()
        raise PermissionError("Use one of: saved, visible, save SSID, forget SSID, join, access-point, access-point-key.")

    def access_point_read(self) -> dict[str, object] | None:
        if self.access_point is None:
            return None
        return {"ssid": self.access_point["ssid"], "uses_default_key": self.access_point["key"] == "deq-tune-bridge"}

    def saved_list(self) -> list[dict[str, object]]:
        return [{"ssid": ssid, "connected": connected} for ssid, connected in sorted(self.saved.items())]
