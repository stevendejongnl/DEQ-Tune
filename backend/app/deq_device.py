"""Holds the one link to the DEQ unit.

The backend owns the link, and the browser does not. This process holds the
handle, so the frontend reads device state over HTTP like any other data.

The configuration picks the transport for that link. `DEQ_TRANSPORT=simulator`
serves a simulated unit that a developer can change while it runs, through
`scripts/deq_console.py`. See `deq_simulator_transport.py`.
`DEQ_TRANSPORT=fake` is the default. It talks to `testing/fake_deq.py`, so the
whole app runs end to end with no hardware. `DEQ_TRANSPORT=accessory` talks to
a real unit through the Pi's accessory gadget. See `accessory_transport.py`.
That transport reaches a DEQ in the car, and the Pi runs it.
`DEQ_TRANSPORT=usb` talks to a unit plugged into this machine's own port
through `usb_transport.py`, which needs the `usb` extra (`uv sync --extra
usb`).

The direct USB transport never answered a real unit. A laptop's USB-C port is
usually host-only hardware, and the DEQ is itself a USB host when connected
this way. See `USB_CAPTURE_NOTES.md` in the outer repo. The Pi answers the
unit, because the gadget presents the device side. So `accessory` is the real
path. `usb` stays only for a machine that can do the same.
`scripts/check_real_deq.py` runs the conformance check over either one.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass

from app.accessory_transport import ACCESSORY_SOCKET_PATH
from app.deq_blob import UserConfiguration
from app.deq_session import DEFAULT_AUDIO_SOURCE, DeqSession, SessionError
from app.deq_transport import Transport, TransportError
from app.eq_data import TuningData

TRANSPORT_ENVIRONMENT_VARIABLE = "DEQ_TRANSPORT"
FAKE_TRANSPORT_NAME = "fake"
SIMULATOR_TRANSPORT_NAME = "simulator"
USB_TRANSPORT_NAME = "usb"
ACCESSORY_TRANSPORT_NAME = "accessory"

# How long the link keeper waits between tries. The unit has a fixed connection
# to the car. So a wait of a few seconds is short against the time a person
# takes to switch the ignition on and open the app.
DEFAULT_RETRY_SECONDS = 3.0

# How long `stop` waits for the loop's thread to finish.
STOP_WAIT_SECONDS = 5.0


class DeviceUnavailable(Exception):
    """The unit is not reachable. The message is for a person to read."""


@dataclass(frozen=True)
class DeviceState:
    """What the header shows about the unit."""

    connected: bool
    firmware_version: str | None = None
    serial: str | None = None
    # Why the link is down, in words a person can act on.
    problem: str | None = None


def build_transport(
    name: str | None = None,
    accessory_socket_path: str = ACCESSORY_SOCKET_PATH,
) -> Transport:
    """Returns the transport that the environment names.

    An unknown name raises an error, and the app does not fall back to the
    fake. A deployment that asks for real hardware and gets a simulation is
    worse than one that refuses to start.
    """
    if name is None:
        name = os.environ.get(TRANSPORT_ENVIRONMENT_VARIABLE, FAKE_TRANSPORT_NAME)
    if name == FAKE_TRANSPORT_NAME:
        from app.testing.fake_deq import FakeDeq

        return FakeDeq()
    if name == SIMULATOR_TRANSPORT_NAME:
        from app.deq_simulator_transport import DeqSimulator

        return DeqSimulator()
    if name == USB_TRANSPORT_NAME:
        from app.usb_transport import UsbTransport

        return UsbTransport()
    if name == ACCESSORY_TRANSPORT_NAME:
        from app.accessory_transport import AccessoryTransport

        return AccessoryTransport(socket_path=accessory_socket_path)
    raise DeviceUnavailable(
        f"no transport named {name!r}. "
        f"Use {TRANSPORT_ENVIRONMENT_VARIABLE}={FAKE_TRANSPORT_NAME}, "
        f"{TRANSPORT_ENVIRONMENT_VARIABLE}={SIMULATOR_TRANSPORT_NAME}, "
        f"{TRANSPORT_ENVIRONMENT_VARIABLE}={ACCESSORY_TRANSPORT_NAME}, "
        f"or {TRANSPORT_ENVIRONMENT_VARIABLE}={USB_TRANSPORT_NAME}."
    )


class DeqDevice:
    """Keeps one DEQ session, and starts it when it is first needed.

    It answers what the unit is and pushes settings to it. You call its methods
    from a route handler. It depends on a transport factory and on
    `DeqSession`.

    One lock guards the link, because two threads reach it: the HTTP handlers,
    and the reconnect thread of `LinkKeeper`. The protocol is one request and
    then its reply, over a single transport. Two threads that write at once
    would interleave frames and put the conversation out of step. The lock
    makes one whole exchange the unit of work, and not one write.
    """

    def __init__(
        self,
        build_transport_function=build_transport,
        after_connect=None,
        source_for_connect=None,
    ) -> None:
        self.build_transport_function = build_transport_function
        # Returns the source mode to set as a link comes up, or None for the
        # default. The person's last choice lives in the database.
        self.source_for_connect = source_for_connect
        # Runs once each time a link comes up, inside the link lock. So a
        # caller sees the unit as connected only after this returns. The
        # active profile goes onto the unit here.
        self.after_connect = after_connect
        # Counts the links that came up. A setting that went onto the unit
        # on an earlier link may be gone after the unit restarted.
        self.link_generation = 0
        self._session: DeqSession | None = None
        self._identity = None
        self._link_lock = threading.RLock()
        # Why the last connection failed, so `state()` can say. Without
        # this the app reports a down link and no reason, and the reason is
        # the only part a person can act on.
        self._problem: str | None = None

    def connect(self) -> DeviceState:
        """Opens the link and runs the unit's startup sequence.

        It first releases the link it already holds. The far end can allow a
        transport only once. The Pi's gadget relays for a single backend,
        because two writers on one DEQ link interleave frames. So a new
        transport built before the old one closes gets a refusal. A real unit
        did that on 2026-10-08. It refused a second `connect()`, and the
        working link went down with it until `LinkKeeper` built it again. The
        fake transport cannot show this, because it refuses nothing.
        """
        with self._link_lock:
            self.disconnect()
            try:
                session = DeqSession(self.build_transport_function())
                session.start(self._source_name_for_connect())
                self._identity = session.read_device_identity()
            except (SessionError, TransportError, DeviceUnavailable) as caught_error:
                self.disconnect()
                self._problem = str(caught_error)
                return DeviceState(connected=False, problem=self._problem)
            self._session = session
            self._problem = None
            self.link_generation += 1
            self._run_after_connect()
            return self.state()

    def _source_name_for_connect(self) -> str:
        """Returns the remembered source mode, or the default one.

        A failed lookup must not cost the link, so it falls back to the
        default too.
        """
        if self.source_for_connect is None:
            return DEFAULT_AUDIO_SOURCE
        try:
            return self.source_for_connect() or DEFAULT_AUDIO_SOURCE
        except Exception:
            return DEFAULT_AUDIO_SOURCE

    def _run_after_connect(self) -> None:
        """Runs the hook, and keeps the link up when the hook fails.

        The hook reports its own failures. A raise here would only throw away
        a link that works.
        """
        if self.after_connect is None:
            return
        try:
            self.after_connect()
        except Exception:
            pass

    def state(self) -> DeviceState:
        """Returns what the header shows, without opening a link."""
        with self._link_lock:
            if self._session is None or self._identity is None:
                return DeviceState(connected=False, problem=self._problem)
            return DeviceState(
                connected=True,
                firmware_version=format_firmware_version(
                    self._identity.firmware_version
                ),
                serial=self._identity.serial,
            )

    def keep_alive(self) -> DeviceState:
        """Sends one keepalive, and drops the link if the unit refuses it.

        It never raises: the keeper's thread has to survive a unit that
        went away, and a dropped link is a normal state the app reports.
        """
        with self._link_lock:
            if self._session is None:
                return self.state()
            try:
                self._session.send_keepalive()
            except (SessionError, TransportError) as caught_error:
                self.disconnect()
                self._problem = str(caught_error)
                return DeviceState(connected=False, problem=self._problem)
            return self.state()

    def disconnect(self) -> None:
        with self._link_lock:
            if self._session is not None:
                self._session.close()
            self._session = None
            self._identity = None

    def require_session(self) -> DeqSession:
        """Returns the live session, or says the unit is not connected."""
        if self._session is None:
            raise DeviceUnavailable("the unit is not connected")
        return self._session

    def write_tuning(self, tuning: TuningData) -> None:
        self.run(lambda session: session.write_tuning(tuning))

    def read_configuration(self) -> UserConfiguration:
        return self.run(lambda session: session.read_user_configuration())

    def run(self, action):
        """Runs one action against the unit, and turns a failure into words.

        A session error means the link is no longer trustworthy. So this method
        drops the link, and `LinkKeeper` opens a new one.

        The lock covers the whole action. One action is one or more
        request-and-reply exchanges. If another thread sent a frame between
        them, that frame would answer the wrong request.
        """
        with self._link_lock:
            session = self.require_session()
            try:
                return action(session)
            except (SessionError, TransportError) as caught_error:
                self.disconnect()
                raise DeviceUnavailable(str(caught_error)) from caught_error


class LinkKeeper:
    """Keeps one device connected, and retries for as long as it runs.

    It calls `connect` until the link is up, and again whenever it drops. You
    `start` it once and `stop` it at shutdown. It depends on a device and on a
    clock it can wait against.

    The app reports the link as a fact, and a user never starts it. The unit
    has a fixed connection to the car. The bridge that holds the USB link
    retries by itself. Both come up with the ignition. So a person has nothing
    useful to press. This class runs the same loop one layer up.

    The caller injects the wait, so a test does not sleep. `wait_function` takes
    a number of seconds and returns True to keep running. That lets `stop`
    interrupt a wait instead of outliving it.
    """

    def __init__(
        self,
        unit: DeqDevice,
        retry_seconds: float = DEFAULT_RETRY_SECONDS,
        wait_function=None,
    ) -> None:
        self.unit = unit
        self.retry_seconds = retry_seconds
        self._stop_requested = threading.Event()
        self.wait_function = wait_function or self._wait_on_event
        self._thread: threading.Thread | None = None

    def _wait_on_event(self, seconds: float) -> bool:
        """Waits, and returns False as soon as a caller calls `stop`."""
        return not self._stop_requested.wait(seconds)

    def start(self) -> None:
        """Starts the loop in its own thread.

        The loop runs in a thread and not in an asyncio task. A transport read
        blocks for its whole timeout. A blocked event loop would stall every
        HTTP request in progress.
        """
        if self._thread is not None:
            return
        self._stop_requested.clear()
        self._thread = threading.Thread(
            target=self.run, name="deq-link-keeper", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Asks the loop to finish, and waits for it to notice."""
        self._stop_requested.set()
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=STOP_WAIT_SECONDS)

    def is_running(self) -> bool:
        """Returns whether the loop's thread is alive."""
        thread = self._thread
        return thread is not None and thread.is_alive()

    def run(self) -> None:
        """Connects, keeps the link warm, and reconnects, until asked to stop.

        A live link still needs a frame now and then. The real app sends
        COMMAND_KEEPALIVE about every nine seconds for a whole session. Nothing
        here sent one until 2026-10-08. The backend connected and then went
        silent. So the app reported a dead link as up, until some other request
        asked the unit for something.

        The keepalive is also the check. If the unit stops answering one, this
        loop drops the link. So `state()` tells the truth, and does not repeat
        what was true at connect time.
        """
        while True:
            if self.unit.state().connected:
                self.unit.keep_alive()
            else:
                self.connect_once()
            if not self.wait_function(self.retry_seconds):
                return

    def connect_once(self) -> DeviceState:
        """Tries one connection and never raises.

        A failure here is a normal state. The car is off, or the bridge has no
        link yet. The reason reaches the app through `DeviceState.problem`. A
        raise would only kill the thread that has to try again.
        """
        try:
            return self.unit.connect()
        except Exception as caught_error:
            # connect() already turns the errors it expects into a state.
            # Anything else still must not stop the retrying.
            return DeviceState(connected=False, problem=str(caught_error))


def format_firmware_version(raw_version: int) -> str:
    """Returns the version the way the app shows it, for example `2.02`.

    The unit sends two bytes. The app's own connect screen reads them as a
    major and a minor part. The `2.02` in the captured accessory string comes
    from there.
    """
    return f"{raw_version >> 8}.{raw_version & 0xFF:02d}"


# The app keeps one unit, so one device object serves every request.
device = DeqDevice()

# One keeper for that device. `main.py` starts it with the app and stops
# it at shutdown.
link_keeper = LinkKeeper(device)
