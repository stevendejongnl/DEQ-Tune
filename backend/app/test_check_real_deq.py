"""Checks the hardware validation script, without hardware.

`scripts/check_real_deq.py` only runs when someone plugs a DEQ in. So nothing
else would catch a break in it. Its checks, run against the fake unit, keep it
honest. The fake answers the way the captures say a real unit does, so every
check should pass against it.
"""

from __future__ import annotations

import pytest

from app.deq_device import DeviceUnavailable
from app.deq_session import DeqSession
from app.deq_transport import TransportError
from app.testing.fake_deq import FakeDeq

check_real_deq = pytest.importorskip("scripts.check_real_deq")


def test_check_link_defaults_to_the_accessory_gadget(monkeypatch) -> None:
    """The app's default is the fake unit. This script's one job is a check of
    a real unit. So its own default transport is `accessory`, the Pi's link to
    a DEQ, and not `fake`."""
    monkeypatch.delenv("DEQ_TRANSPORT", raising=False)
    report = check_real_deq.Report()
    # No gadget relays on this machine, so the open always fails here. This
    # test only checks, by its error, that the script tried the accessory
    # transport and not a hardcoded "fake" one.
    with pytest.raises(TransportError, match="could not reach the gadget"):
        check_real_deq.check_link(report)


def test_check_link_rejects_the_fake_transport(monkeypatch) -> None:
    """A check against the fake unit says nothing about a real one, which
    is this script's whole point."""
    monkeypatch.setenv("DEQ_TRANSPORT", "fake")
    report = check_real_deq.Report()
    with pytest.raises(TransportError, match="checks nothing about a real unit"):
        check_real_deq.check_link(report)


def test_check_link_reports_an_unknown_transport_name(monkeypatch) -> None:
    monkeypatch.setenv("DEQ_TRANSPORT", "not-a-real-transport")
    report = check_real_deq.Report()
    with pytest.raises(DeviceUnavailable, match="no transport named"):
        check_real_deq.check_link(report)




def run_every_check() -> check_real_deq.Report:
    report = check_real_deq.Report()
    session = DeqSession(FakeDeq())
    check_real_deq.check_startup(report, session)
    check_real_deq.check_identity(report, session)
    check_real_deq.check_configuration(report, session)
    check_real_deq.check_keepalive(report, session)
    check_real_deq.check_write_back(report, session)
    return report


def test_every_check_passes_against_the_fake_unit(capsys) -> None:
    report = run_every_check()
    capsys.readouterr()
    assert report.failures == []
    assert report.differences == []


def test_the_report_says_so_when_nothing_differed(capsys) -> None:
    report = run_every_check()
    assert report.summarise() == 0
    assert "Every check matched" in capsys.readouterr().out


def test_a_difference_is_reported_and_changes_the_exit_code(capsys) -> None:
    report = check_real_deq.Report()
    report.differs("blob size", "600 bytes, not the 572 expected")
    assert report.summarise() == 1
    output = capsys.readouterr().out
    assert "DIFFERS" in output
    assert "USB_CAPTURE_NOTES.md" in output


def test_a_failure_changes_the_exit_code(capsys) -> None:
    report = check_real_deq.Report()
    report.failed("command 0x09", "the unit sent nothing")
    assert report.summarise() == 1
    assert "failed outright" in capsys.readouterr().out


def test_the_blob_check_reads_a_real_units_reply_shape() -> None:
    """The blob is not the whole reply. A real unit answered 0x09 with a
    2032-byte body: STATUS, the 572-byte blob, then bytes that have no meaning
    for this app. So the check has to cut the blob out and still pass.
    """
    report = check_real_deq.Report()
    session = DeqSession(FakeDeq())
    check_real_deq.check_configuration(report, session)
    assert report.failures == []
    assert report.differences == []
