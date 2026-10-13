"""Checks that a fault which fixes itself is still visible afterwards.

The notice log exists for that purpose. So most of these tests raise a
condition, let it pass, and then assert that the notice is still there.
"""

from __future__ import annotations

from app.bridge_health import BridgeHealth
from app.bridge_notices import (
    SEVERITY_INFO,
    SEVERITY_WARNING,
    UNDERVOLTAGE_NOTICE_KEY,
    BridgeNoticeLog,
    note_undervoltage,
)


class StoppedClock:
    """A clock a test moves by hand.

    It answers the time, and `BridgeNoticeLog` reads it. It depends on nothing.
    Real time would make "first seen" and "last seen" untestable without a
    sleep.
    """

    def __init__(self, seconds: float = 0.0) -> None:
        self.seconds = seconds

    def __call__(self) -> float:
        return self.seconds

    def advance(self, seconds: float) -> None:
        self.seconds += seconds


def test_a_new_log_holds_nothing():
    assert BridgeNoticeLog().notices() == []
    assert BridgeNoticeLog().has_warning() is False


def test_a_notice_stays_after_the_condition_passes():
    """The reason this class exists. A dip that lasted a second must not
    vanish from the app the moment the voltage recovers."""
    log = BridgeNoticeLog()

    note_undervoltage(log, BridgeHealth(undervoltage_now=True))
    # The supply recovers. Nothing raises a notice now.
    note_undervoltage(log, BridgeHealth(undervoltage_now=False,
                                        undervoltage_since_boot=False))

    assert [notice.key for notice in log.notices()] == [UNDERVOLTAGE_NOTICE_KEY]
    assert log.has_warning() is True


def test_the_since_boot_flag_alone_raises_the_notice():
    """The hardware's own sticky bit. The dip is over, and it still
    explains why the link dropped earlier."""
    log = BridgeNoticeLog()

    note_undervoltage(log, BridgeHealth(undervoltage_now=False,
                                        undervoltage_since_boot=True))

    assert log.has_warning() is True


def test_a_healthy_bridge_raises_nothing():
    log = BridgeNoticeLog()

    note_undervoltage(log, BridgeHealth(undervoltage_now=False,
                                        undervoltage_since_boot=False))

    assert log.notices() == []


def test_a_machine_that_cannot_tell_raises_nothing():
    """A laptop reports None, which is not a fault."""
    log = BridgeNoticeLog()

    note_undervoltage(log, BridgeHealth())

    assert log.notices() == []


def test_the_same_condition_is_one_notice_with_a_count():
    clock = StoppedClock()
    log = BridgeNoticeLog(clock=clock)

    log.raise_notice("a-key", SEVERITY_WARNING, "first message")
    clock.advance(30.0)
    log.raise_notice("a-key", SEVERITY_WARNING, "a later message")

    notices = log.notices()
    assert len(notices) == 1
    assert notices[0].count == 2


def test_the_first_message_is_kept_not_the_newest():
    """The first sighting says when the trouble started, which is what a
    person reading the list afterwards needs."""
    log = BridgeNoticeLog()

    log.raise_notice("a-key", SEVERITY_WARNING, "first message")
    log.raise_notice("a-key", SEVERITY_WARNING, "a later message")

    assert log.notices()[0].message == "first message"


def test_the_times_say_when_it_started_and_when_it_last_happened():
    clock = StoppedClock(seconds=100.0)
    log = BridgeNoticeLog(clock=clock)

    log.raise_notice("a-key", SEVERITY_WARNING, "message")
    clock.advance(45.0)
    log.raise_notice("a-key", SEVERITY_WARNING, "message")

    notice = log.notices()[0]
    assert notice.first_seen_seconds == 100.0
    assert notice.last_seen_seconds == 145.0


def test_warnings_come_before_notes():
    log = BridgeNoticeLog()

    log.raise_notice("a-note", SEVERITY_INFO, "worth knowing")
    log.raise_notice("a-fault", SEVERITY_WARNING, "worth acting on")

    assert [notice.key for notice in log.notices()] == ["a-fault", "a-note"]


def test_the_newest_of_two_warnings_comes_first():
    clock = StoppedClock()
    log = BridgeNoticeLog(clock=clock)

    log.raise_notice("older", SEVERITY_WARNING, "message")
    clock.advance(10.0)
    log.raise_notice("newer", SEVERITY_WARNING, "message")

    assert [notice.key for notice in log.notices()] == ["newer", "older"]


def test_two_conditions_are_two_notices():
    log = BridgeNoticeLog()

    log.raise_notice("one", SEVERITY_WARNING, "message")
    log.raise_notice("two", SEVERITY_WARNING, "message")

    assert len(log.notices()) == 2


def test_clearing_forgets_everything():
    """What a restart does. Only a person asks for this. A request does not, or
    the sticky notice would not be sticky."""
    log = BridgeNoticeLog()
    log.raise_notice("a-key", SEVERITY_WARNING, "message")

    log.clear()

    assert log.notices() == []
    assert log.has_warning() is False


def test_a_note_alone_is_not_a_warning():
    log = BridgeNoticeLog()

    log.raise_notice("a-note", SEVERITY_INFO, "worth knowing")

    assert log.has_warning() is False
    assert len(log.notices()) == 1
