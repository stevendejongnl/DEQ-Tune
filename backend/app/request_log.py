"""Writes one line per HTTP request, so a log can show whether a request arrived.

On 2026-10-24 an access point key save from the phone never reached the
Wi-Fi helper, and no log could say whether the request reached the
backend. Uvicorn's own access log had no time and no duration, and the
status polls buried every other line.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Awaitable, Callable, MutableMapping
from datetime import datetime
from typing import Any

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
AsgiApp = Callable[[Scope, Receive, Send], Awaitable[None]]

# The frontend and the Pi's own services ask for these every few seconds.
# A poll that succeeds says nothing, so the log leaves it out. A poll that
# fails is still written.
POLL_PATHS = frozenset({"/api/device", "/health"})

# The status a request gets when the app raises before it starts a response.
STATUS_WHEN_THE_APP_FAILED = 500


def write_to_standard_error(line: str) -> None:
    """Writes one line where systemd sends the backend's output."""
    print(line, file=sys.stderr, flush=True)


def is_quiet_poll(method: str, path: str, status: int) -> bool:
    """Tells whether a request is a successful status poll."""
    return method == "GET" and path in POLL_PATHS and status < 400


def format_request_line(
    moment: datetime, method: str, path: str, status: int, duration_ms: float, client: str
) -> str:
    """Returns the log line of one request.

    The line holds the path only. A query string or a body can carry a key
    or a password, so neither goes into the log.
    """
    timestamp = moment.strftime("%Y-%m-%d %H:%M:%S")
    return f"{timestamp} request {method} {path} {status} {duration_ms:.0f} ms from {client}"


class RequestLog:
    """ASGI middleware that writes one line for each HTTP request.

    Wrap the app with it. `write_line` takes each line, `now` gives the
    time on the line, and `clock` measures the duration.
    """

    def __init__(
        self,
        app: AsgiApp,
        write_line: Callable[[str], None] = write_to_standard_error,
        now: Callable[[], datetime] = datetime.now,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app = app
        self.write_line = write_line
        self.now = now
        self.clock = clock

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = self.clock()
        status = STATUS_WHEN_THE_APP_FAILED

        async def send_and_note_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_and_note_status)
        finally:
            self.write_request(scope, status, self.clock() - started)

    def write_request(self, scope: Scope, status: int, duration_seconds: float) -> None:
        method = scope["method"]
        path = scope["path"]
        if is_quiet_poll(method, path, status):
            return
        client = scope.get("client")
        client_host = client[0] if client else "unknown"
        self.write_line(
            format_request_line(
                self.now(), method, path, status, duration_seconds * 1000, client_host
            )
        )
