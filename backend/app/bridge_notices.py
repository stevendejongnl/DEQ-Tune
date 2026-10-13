"""What went wrong on the bridge, kept until it restarts.

A person must see a fault even when it fixes itself. A Pi that browns out for a
second drops its USB link and its Wi-Fi, then recovers. The person with the
phone then has an app that misbehaved for no visible reason. By the time anyone
looks, every live reading is healthy again.

So the store raises a notice once, and the notice **stays** for as long as the
process runs. The store does not clear it when the condition passes, on
purpose. A restart of the bridge clears them. That matches the hardware's own
sticky undervoltage bit, and gives a person one obvious way to start clean.

The same store serves anything else worth remembering about a session: a link
that dropped, an audio feed that died. The store raises each notice under a
key. So a condition that keeps coming back is one notice with a count and a
last-seen time, and not a thousand rows.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class BridgeNotice:
    """One thing that went wrong, and how often."""

    key: str
    severity: str
    message: str
    first_seen_seconds: float
    last_seen_seconds: float
    count: int


# What a notice can be. `warning` is a fault a person should act on. `info` is
# worth knowing and needs no action.
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


class BridgeNoticeLog:
    """Remembers what went wrong, until the bridge restarts.

    It raises and lists notices. The device code and the health reader call
    `raise_notice`, and the API reads `notices`. It depends on a clock that a
    caller can give it.

    One lock guards the store, because the link keeper's thread and the request
    handlers both reach it.
    """

    def __init__(self, clock=time.monotonic) -> None:
        self.clock = clock
        self._notices: dict[str, BridgeNotice] = {}
        self._lock = threading.Lock()

    def raise_notice(self, key: str, severity: str, message: str) -> BridgeNotice:
        """Records one fault, or counts another sighting of a known one.

        The store keeps the first message, and not the newest. The first one
        says when the trouble started. A person who reads the list afterwards
        needs that.
        """
        now = self.clock()
        with self._lock:
            existing = self._notices.get(key)
            if existing is None:
                notice = BridgeNotice(
                    key=key,
                    severity=severity,
                    message=message,
                    first_seen_seconds=now,
                    last_seen_seconds=now,
                    count=1,
                )
            else:
                notice = BridgeNotice(
                    key=existing.key,
                    severity=existing.severity,
                    message=existing.message,
                    first_seen_seconds=existing.first_seen_seconds,
                    last_seen_seconds=now,
                    count=existing.count + 1,
                )
            self._notices[key] = notice
            return notice

    def notices(self) -> list[BridgeNotice]:
        """Returns every notice, the worst and newest first."""
        with self._lock:
            found = list(self._notices.values())
        found.sort(
            key=lambda notice: (
                notice.severity != SEVERITY_WARNING,
                -notice.last_seen_seconds,
            )
        )
        return found

    def has_warning(self) -> bool:
        with self._lock:
            return any(
                notice.severity == SEVERITY_WARNING
                for notice in self._notices.values()
            )

    def clear(self) -> None:
        """Forgets everything. A restart does this, and a request must not.

        It exists for tests, and for a person who has read the list and wants
        to see whether the trouble comes back.
        """
        with self._lock:
            self._notices.clear()


# Keys, so one condition is one notice however often it comes back.
UNDERVOLTAGE_NOTICE_KEY = "undervoltage"

# Short enough for a header on a phone. The detail belongs in the log,
# not in a pill a person reads while the car is running.
UNDERVOLTAGE_MESSAGE = "Power dip on the bridge — check the supply"


def note_undervoltage(notice_log: BridgeNoticeLog, health) -> None:
    """Raises a notice when the bridge reports a power dip.

    Both flags count. `undervoltage_now` means a dip is in progress. The
    hardware keeps the since-boot flag for us. Because of that flag, a dip that
    lasted a moment is still visible an hour later.
    """
    if health.undervoltage_now or health.undervoltage_since_boot:
        notice_log.raise_notice(
            UNDERVOLTAGE_NOTICE_KEY, SEVERITY_WARNING, UNDERVOLTAGE_MESSAGE
        )


# The app keeps one bridge, so one log serves every request.
notice_log = BridgeNoticeLog()
