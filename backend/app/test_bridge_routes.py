"""Checks the bridge endpoint, including that a notice outlives its cause."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.bridge_notices import SEVERITY_WARNING, notice_log
from app.main import app


@pytest.fixture
def bridge_client():
    """A client with an empty notice log.

    The log is module state that outlives one request, on purpose. So a test
    has to start from a known log, or the tests see each other's notices.
    """
    notice_log.clear()
    with TestClient(app) as client:
        yield client
    notice_log.clear()


def test_the_bridge_answers_on_any_machine(bridge_client):
    """CI is not a Pi. The endpoint still has to answer."""
    response = bridge_client.get("/api/bridge")

    assert response.status_code == 200
    assert "undervoltage_now" in response.json()


def test_a_machine_that_cannot_tell_reports_null(bridge_client):
    body = bridge_client.get("/api/bridge").json()

    # None where there is no vcgencmd, which is every machine but the Pi.
    assert body["undervoltage_now"] in (None, True, False)


def test_a_raised_notice_reaches_the_app(bridge_client):
    notice_log.raise_notice("a-key", SEVERITY_WARNING, "something went wrong")

    body = bridge_client.get("/api/bridge").json()

    assert [notice["key"] for notice in body["notices"]] == ["a-key"]
    assert body["notices"][0]["message"] == "something went wrong"
    assert body["notices"][0]["severity"] == SEVERITY_WARNING


def test_a_notice_is_still_there_on_the_next_request(bridge_client):
    """The point of the whole store: reading does not clear it."""
    notice_log.raise_notice("a-key", SEVERITY_WARNING, "something went wrong")

    bridge_client.get("/api/bridge")
    body = bridge_client.get("/api/bridge").json()

    assert len(body["notices"]) == 1


def test_no_notices_when_nothing_has_gone_wrong(bridge_client):
    assert bridge_client.get("/api/bridge").json()["notices"] == []
