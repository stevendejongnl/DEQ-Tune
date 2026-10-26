"""Checks the request log."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.request_log import RequestLog

FIXED_MOMENT = datetime(2026, 10, 24, 18, 30, 5)


class SteppingClock:
    """A clock that moves a fixed step each time something reads it."""

    def __init__(self, step_seconds: float) -> None:
        self.step_seconds = step_seconds
        self.seconds = 0.0

    def __call__(self) -> float:
        self.seconds += self.step_seconds
        return self.seconds


def build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/device")
    def device() -> dict[str, bool]:
        return {"connected": True}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.put("/api/wifi/access-point/key")
    def save_key(body: dict[str, str]) -> dict[str, bool]:
        return {"saved": True}

    @app.get("/api/broken")
    def broken() -> None:
        raise RuntimeError("the handler failed")

    @app.get("/api/missing")
    def missing() -> None:
        raise HTTPException(status_code=404)

    return app


@pytest.fixture(name="lines")
def lines_fixture() -> list[str]:
    return []


@pytest.fixture(name="client")
def client_fixture(lines: list[str]) -> TestClient:
    logged_app = RequestLog(
        build_app(),
        write_line=lines.append,
        now=lambda: FIXED_MOMENT,
        clock=SteppingClock(0.042),
    )
    return TestClient(logged_app, raise_server_exceptions=False)


def test_a_request_gets_one_line_with_time_status_and_duration(client, lines):
    client.put("/api/wifi/access-point/key", json={"key": "secret-key-1234"})

    assert lines == [
        "2026-10-24 18:30:05 request PUT /api/wifi/access-point/key 200 42 ms from testclient"
    ]


def test_the_line_holds_no_body_and_no_query_string(client, lines):
    client.put("/api/wifi/access-point/key?key=query-secret", json={"key": "body-secret"})

    assert "secret" not in lines[0]


def test_a_successful_poll_writes_no_line(client, lines):
    client.get("/api/device")
    client.get("/health")

    assert lines == []


def test_a_failed_request_is_written(client, lines):
    client.get("/api/missing")

    assert lines == ["2026-10-24 18:30:05 request GET /api/missing 404 42 ms from testclient"]


def test_a_request_whose_handler_raises_is_written_as_500(client, lines):
    client.get("/api/broken")

    assert lines == ["2026-10-24 18:30:05 request GET /api/broken 500 42 ms from testclient"]
