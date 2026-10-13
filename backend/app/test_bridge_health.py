"""Checks the bridge health report, on a machine that is not a Pi.

Everything here runs without `vcgencmd`, on purpose. The report has to answer
on a laptop and in CI, and not only on the Pi it describes.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.bridge_health import (
    UNDERVOLTAGE_NOW_FLAG,
    UNDERVOLTAGE_SINCE_BOOT_FLAG,
    read_bridge_health,
    read_throttled_flags,
    read_uptime_seconds,
)


@dataclass
class FakeCompletedCommand:
    stdout: str


class FakeVcgencmd:
    """Answers as `vcgencmd get_throttled` does, with chosen flags.

    It returns one line of output, and `read_throttled_flags` calls it. It
    depends on nothing. A test picks the flags, and needs no Pi in the right
    state.
    """

    def __init__(self, output: str) -> None:
        self.output = output
        self.calls: list[list[str]] = []

    def __call__(self, arguments, **keyword_arguments) -> FakeCompletedCommand:
        self.calls.append(arguments)
        return FakeCompletedCommand(stdout=self.output)


class MissingVcgencmd:
    """Fails the way a machine with no `vcgencmd` does."""

    def __call__(self, arguments, **keyword_arguments):
        raise FileNotFoundError("vcgencmd")


def test_a_healthy_pi_reports_no_undervoltage():
    health = read_bridge_health(run_command=FakeVcgencmd("throttled=0x0"))

    assert health.undervoltage_now is False
    assert health.undervoltage_since_boot is False


def test_an_undervoltage_now_is_reported():
    health = read_bridge_health(
        run_command=FakeVcgencmd(f"throttled=0x{UNDERVOLTAGE_NOW_FLAG:x}")
    )

    assert health.undervoltage_now is True


def test_an_undervoltage_earlier_this_boot_is_reported():
    """The flag a brown-out leaves behind. It explains a past fault that
    is no longer happening, which is otherwise unexplainable."""
    health = read_bridge_health(
        run_command=FakeVcgencmd(f"throttled=0x{UNDERVOLTAGE_SINCE_BOOT_FLAG:x}")
    )

    assert health.undervoltage_now is False
    assert health.undervoltage_since_boot is True


def test_both_flags_together_are_reported():
    flags = UNDERVOLTAGE_NOW_FLAG | UNDERVOLTAGE_SINCE_BOOT_FLAG
    health = read_bridge_health(run_command=FakeVcgencmd(f"throttled=0x{flags:x}"))

    assert health.undervoltage_now is True
    assert health.undervoltage_since_boot is True


def test_a_machine_with_no_vcgencmd_says_it_does_not_know():
    """A laptop and CI take this path. `False` would be a claim the
    machine cannot make, so the answer is None."""
    health = read_bridge_health(run_command=MissingVcgencmd())

    assert health.undervoltage_now is None
    assert health.undervoltage_since_boot is None


def test_output_that_cannot_be_read_is_not_a_crash():
    health = read_bridge_health(run_command=FakeVcgencmd("throttled=banana"))

    assert health.undervoltage_now is None


def test_empty_output_is_not_a_crash():
    assert read_throttled_flags(run_command=FakeVcgencmd("")) is None


def test_the_uptime_comes_from_procfs(tmp_path):
    uptime_file = tmp_path / "uptime"
    uptime_file.write_text("3812.04 7600.11\n")

    assert read_uptime_seconds(str(uptime_file)) == 3812.04


def test_a_missing_uptime_file_is_not_a_crash(tmp_path):
    assert read_uptime_seconds(str(tmp_path / "absent")) is None


def test_the_uptime_is_reported_even_with_no_vcgencmd(tmp_path):
    """The two readings are independent: a laptop still knows its uptime."""
    uptime_file = tmp_path / "uptime"
    uptime_file.write_text("120.0 240.0\n")

    health = read_bridge_health(
        run_command=MissingVcgencmd(), uptime_path=str(uptime_file)
    )

    assert health.undervoltage_now is None
    assert health.uptime_seconds == 120.0
