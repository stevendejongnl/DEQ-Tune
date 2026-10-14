"""Checks transport selection. That part of deq_device.py needs no running
device to test: which transport a name picks, and what an unknown or incomplete
one reports.
"""

from __future__ import annotations

import time

import pytest

from app.accessory_transport import AccessoryUnavailable
from app.deq_device import (
    ACCESSORY_TRANSPORT_NAME,
    FAKE_TRANSPORT_NAME,
    USB_TRANSPORT_NAME,
    DeqDevice,
    DeviceState,
    DeviceUnavailable,
    LinkKeeper,
    build_transport,
)
from app.deq_transport import TransportError
from app.testing.fake_deq import FakeDeq
from app.usb_transport import UsbUnavailable


def test_fake_is_the_default():
    assert isinstance(build_transport(), FakeDeq)


def test_fake_can_be_named_explicitly():
    assert isinstance(build_transport(FAKE_TRANSPORT_NAME), FakeDeq)


def test_an_unknown_name_is_an_error():
    with pytest.raises(DeviceUnavailable, match="no transport named"):
        build_transport("not-a-real-transport")


def test_accessory_without_the_gadget_running_says_what_to_check():
    """The gadget's socket exists only while a DEQ session runs. So a developer
    who asks for the real transport on a laptop gets this result.
    `AccessoryTransport` itself reaches the socket. So its failure comes back
    as the transport's own error, and not wrapped in `DeviceUnavailable`.
    `DeqDevice.connect()` catches `TransportError` and turns it into a reported
    problem. `build_transport` itself does not."""
    with pytest.raises(AccessoryUnavailable, match="could not reach the gadget"):
        build_transport(ACCESSORY_TRANSPORT_NAME)


def test_usb_with_no_pyusb_installed_says_so():
    """`usb` is an optional extra. CI never installs it, so CI runs this path.
    `UsbUnavailable` is the transport's own error, not `DeviceUnavailable`."""
    try:
        import usb.core  # noqa: F401

        pytest.skip("pyusb is installed in this environment")
    except ModuleNotFoundError:
        pass
    with pytest.raises(UsbUnavailable, match="pyusb is not installed"):
        build_transport(USB_TRANSPORT_NAME)


class RecordingWait:
    """Answers the keeper's waits, and stops it after a set number.

    It counts the waits and returns False on the last one. `LinkKeeper` calls
    it in place of a sleep. It depends on nothing. Without this a test of a
    retry loop would have to sleep in real time.
    """

    def __init__(self, allowed_waits: int) -> None:
        self.allowed_waits = allowed_waits
        self.waited_seconds: list[float] = []

    def __call__(self, seconds: float) -> bool:
        self.waited_seconds.append(seconds)
        return len(self.waited_seconds) < self.allowed_waits


class CountingDevice:
    """A device that records connect calls and reports a chosen state.

    It stands in for `DeqDevice`, and `LinkKeeper` drives it. It depends on
    nothing. `connect_results` gives one state per call, so a test can say
    "fail, fail, then succeed".
    """

    def __init__(self, connect_results: list[DeviceState]) -> None:
        self.connect_results = list(connect_results)
        self.connect_count = 0
        self.keep_alive_count = 0
        self._state = DeviceState(connected=False)

    def connect(self) -> DeviceState:
        self.connect_count += 1
        if self.connect_results:
            self._state = self.connect_results.pop(0)
        return self._state

    def keep_alive(self) -> DeviceState:
        """Counts the keepalives the keeper sends on a live link."""
        self.keep_alive_count += 1
        return self._state

    def state(self) -> DeviceState:
        return self._state

    def drop_link(self, problem: str) -> None:
        """Leaves the state a failed action leaves behind."""
        self._state = DeviceState(connected=False, problem=problem)


class RaisingDevice:
    """A device whose connect raises instead of reporting a problem.

    `DeqDevice.connect` turns the errors it expects into a state, but a
    transport can raise something else. The keeper must survive that, or
    the thread dies and nothing reconnects.
    """

    def __init__(self) -> None:
        self.connect_count = 0

    def connect(self) -> DeviceState:
        self.connect_count += 1
        raise RuntimeError("the bridge is not there")

    def state(self) -> DeviceState:
        return DeviceState(connected=False)


def test_the_keeper_connects_without_being_asked():
    """The whole point: no user action starts the link."""
    unit = CountingDevice([DeviceState(connected=True)])
    wait = RecordingWait(allowed_waits=1)

    LinkKeeper(unit, wait_function=wait).run()

    assert unit.connect_count == 1
    assert unit.state().connected is True


def test_the_keeper_stops_trying_once_the_link_is_up():
    """A connected unit must not be reconnected. Opening a second session
    on a live link would leave two writers on one transport."""
    unit = CountingDevice([DeviceState(connected=True)])
    wait = RecordingWait(allowed_waits=4)

    LinkKeeper(unit, wait_function=wait).run()

    assert unit.connect_count == 1


def test_the_keeper_keeps_a_live_link_warm():
    """The real app sends COMMAND_KEEPALIVE for a whole session. Nothing
    here sent one until 2026-10-08: the backend connected and then went
    silent, so a dead link kept reporting itself as up."""
    unit = CountingDevice([DeviceState(connected=True)])
    wait = RecordingWait(allowed_waits=4)

    LinkKeeper(unit, wait_function=wait).run()

    assert unit.keep_alive_count > 0
    assert unit.connect_count == 1


def test_the_keeper_tries_again_after_a_failure():
    """The car is off, then it is on. Nobody presses anything between."""
    unit = CountingDevice(
        [
            DeviceState(connected=False, problem="the unit is not connected"),
            DeviceState(connected=False, problem="the unit is not connected"),
            DeviceState(connected=True),
        ]
    )
    wait = RecordingWait(allowed_waits=5)

    LinkKeeper(unit, wait_function=wait).run()

    assert unit.connect_count == 3
    assert unit.state().connected is True


def test_the_keeper_reconnects_when_a_live_link_drops():
    """`DeqDevice.run` drops the link when a session fails, so the keeper
    has to notice and open a new one."""
    unit = CountingDevice([DeviceState(connected=True)])
    wait = RecordingWait(allowed_waits=4)
    keeper = LinkKeeper(unit, wait_function=wait)

    keeper.connect_once()
    assert unit.connect_count == 1

    unit.drop_link("the link failed")

    keeper.run()

    assert unit.connect_count > 1


def test_a_raising_connect_does_not_stop_the_keeper():
    unit = RaisingDevice()
    wait = RecordingWait(allowed_waits=3)

    LinkKeeper(unit, wait_function=wait).run()

    assert unit.connect_count == 3


def test_a_raising_connect_is_reported_as_a_problem():
    state = LinkKeeper(RaisingDevice()).connect_once()

    assert state.connected is False
    assert "the bridge is not there" in state.problem


def test_the_keeper_waits_the_interval_it_was_given():
    unit = CountingDevice([DeviceState(connected=True)])
    wait = RecordingWait(allowed_waits=3)

    LinkKeeper(unit, retry_seconds=1.5, wait_function=wait).run()

    assert wait.waited_seconds == [1.5, 1.5, 1.5]


def test_the_keeper_connects_a_real_device_to_the_fake_unit():
    """End to end against `FakeDeq`, so the test proves the loop against the
    real `DeqDevice` and not only against a stand-in."""
    unit = DeqDevice(build_transport_function=FakeDeq)
    wait = RecordingWait(allowed_waits=1)

    LinkKeeper(unit, wait_function=wait).run()

    state = unit.state()
    assert state.connected is True
    assert state.firmware_version is not None


def test_start_and_stop_run_the_loop_in_a_thread():
    """`start` must connect, and `stop` must end the thread."""
    unit = DeqDevice(build_transport_function=FakeDeq)
    keeper = LinkKeeper(unit, retry_seconds=0.01)

    keeper.start()
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not unit.state().connected:
            time.sleep(0.01)
        assert unit.state().connected is True
    finally:
        keeper.stop()

    assert keeper.is_running() is False


def test_a_down_link_reports_why_it_is_down():
    # The reason is the only part of a failure a person can act on. An
    # earlier version returned a bare state from `state()`, so the app
    # showed a down link and no reason.
    def build_refusing_transport():
        raise DeviceUnavailable("the unit is not plugged in")

    device = DeqDevice(build_refusing_transport)
    assert device.connect().problem == "the unit is not plugged in"
    assert device.state().problem == "the unit is not plugged in"
    assert device.state().connected is False


def test_a_link_that_comes_up_forgets_the_old_reason():
    attempts = []

    def build_transport_that_recovers():
        attempts.append(1)
        if len(attempts) == 1:
            raise DeviceUnavailable("the car is off")
        return FakeDeq()

    device = DeqDevice(build_transport_that_recovers)
    assert device.connect().problem == "the car is off"
    assert device.connect().problem is None
    assert device.state().problem is None
    assert device.state().connected is True


class SingleLinkFakeDeq(FakeDeq):
    """A fake unit that allows one open link at a time, like the Pi's relay.

    The gadget relays for a single backend, because two writers on one DEQ link
    interleave frames. So it refuses a second transport while the first is
    open. You build these through `open_link`. It depends on the counter that
    tracks how many are open.

    `FakeDeq` alone cannot catch a second open, because it allows any number.
    This seam makes the refusal visible to a test.
    """

    def __init__(self, open_links: list) -> None:
        super().__init__()
        self.open_links = open_links

    def close(self) -> None:
        if self in self.open_links:
            self.open_links.remove(self)
        super().close()


def open_single_link(open_links: list) -> SingleLinkFakeDeq:
    """Returns a new link, or refuses because one is already open."""
    if open_links != []:
        raise TransportError(
            "a second backend tried to attach; the gadget refused it"
        )
    transport = SingleLinkFakeDeq(open_links)
    open_links.append(transport)
    return transport


def test_connecting_twice_releases_the_first_link_instead_of_being_refused():
    """A real unit refused this on 2026-10-08, and the working link went
    down with the refusal. `connect` has to let go of the link it holds
    before it asks for another, because the far end allows only one."""
    open_links: list = []
    unit = DeqDevice(build_transport_function=lambda: open_single_link(open_links))

    first = unit.connect()
    assert first.connected is True

    second = unit.connect()

    assert second.connected is True, second.problem
    assert second.problem is None
    assert len(open_links) == 1, "the first link was left open"


class FailsOnKeepalive(FakeDeq):
    """Answers the connect sequence, then refuses the next keepalive.

    It plays a unit that went away mid-session: the car switched off, or the
    cable moved. You connect, then the first keepalive fails. It depends on
    nothing beyond `FakeDeq`.
    """

    def __init__(self) -> None:
        super().__init__()
        self.connected_once = False

    def send_frame(self, frame: bytes) -> None:
        if self.connected_once:
            raise TransportError("the unit stopped answering")
        super().send_frame(frame)


def test_a_failing_keepalive_drops_the_link_and_says_why():
    """A keepalive is the only thing that notices a unit that went away
    between requests. Reporting `connected` after one fails would tell the
    app a link is up when it is gone."""
    unit = DeqDevice(build_transport_function=FailsOnKeepalive)
    assert unit.connect().connected is True

    unit.require_session().transport.connected_once = True
    state = unit.keep_alive()

    assert state.connected is False
    assert "stopped answering" in state.problem


def test_keeping_a_dead_link_alive_is_harmless():
    """The keeper calls this on whatever state it finds, so it must not
    raise when there is no session to keep."""
    unit = DeqDevice(build_transport_function=FakeDeq)

    state = unit.keep_alive()

    assert state.connected is False


def test_the_after_connect_hook_runs_once_per_new_link():
    calls = []
    unit = DeqDevice(build_transport_function=FakeDeq, after_connect=lambda: calls.append(1))

    unit.connect()
    unit.connect()

    assert calls == [1, 1]
    assert unit.link_generation == 2


def test_a_hook_that_raises_keeps_the_link_up():
    """The hook reports its own failures. The link it failed on still works."""

    def failing_hook() -> None:
        raise RuntimeError("the profile could not go on")

    unit = DeqDevice(build_transport_function=FakeDeq, after_connect=failing_hook)

    assert unit.connect().connected
