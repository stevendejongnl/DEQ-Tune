"""Checks the bridge's machine statistics against a hand-written file system.

Each test builds the few procfs and sysfs files it needs in a temporary
directory, and points the readers there. No test depends on the machine that
runs it.
"""

from __future__ import annotations

import json
from collections import namedtuple
from dataclasses import dataclass
from pathlib import Path

from app.bridge_system import (
    SystemSources,
    parse_kibibyte_fields,
    parse_os_release,
    parse_wireless_signals,
    read_bridge_system,
)

DiskUsage = namedtuple("DiskUsage", "total used free")

IP_ADDRESSES = [
    {"ifname": "lo", "operstate": "UNKNOWN", "address": "00:00:00:00:00:00", "addr_info": []},
    {
        "ifname": "wlan0",
        "operstate": "UP",
        "address": "b8:27:eb:00:00:01",
        "addr_info": [{"family": "inet", "local": "192.168.4.1", "prefixlen": 24}],
    },
]


@dataclass
class FakeCompletedCommand:
    stdout: str


class FakeCommands:
    """Answers `ip -j addr` and `vcgencmd get_throttled` as a Pi does.

    The readers call it in place of `subprocess.run`. It depends on nothing.
    """

    def __init__(self, throttled: str = "throttled=0x50000") -> None:
        self.throttled = throttled

    def __call__(self, arguments, **keyword_arguments) -> FakeCompletedCommand:
        if arguments[0] == "ip":
            return FakeCompletedCommand(stdout=json.dumps(IP_ADDRESSES))
        if arguments[0] == "vcgencmd":
            return FakeCompletedCommand(stdout=self.throttled)
        raise FileNotFoundError(arguments[0])


def missing_command(arguments, **keyword_arguments):
    raise FileNotFoundError(arguments[0])


def write_file(root: Path, relative_path: str, text: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def fake_pi(root: Path) -> SystemSources:
    """A Pi Zero 2 W, as its own files describe it."""
    write_file(root, "proc/meminfo", "MemTotal:  425000 kB\nMemAvailable: 200000 kB\nSwapTotal: 102396 kB\nSwapFree: 102396 kB\n")
    write_file(root, "proc/self/status", "Name:\tpython\nVmRSS:\t   51200 kB\n")
    write_file(root, "proc/loadavg", "0.12 0.34 0.56 1/123 4567\n")
    write_file(root, "proc/uptime", "3600.50 7000.00\n")
    write_file(root, "proc/cpuinfo", "processor\t: 0\n\nprocessor\t: 1\n\nprocessor\t: 2\n\nprocessor\t: 3\n")
    write_file(root, "proc/device-tree/model", "Raspberry Pi Zero 2 W Rev 1.0\x00")
    write_file(root, "proc/sys/kernel/hostname", "deq\n")
    write_file(root, "proc/sys/kernel/osrelease", "6.6.51+rpt-rpi-v8\n")
    write_file(root, "proc/net/wireless", "Inter-| sta-|   Quality\n face | tus | link level noise\n wlan0: 0000   55.  -61.  -256 0 0 0 0 0 0\n")
    write_file(root, "etc/os-release", 'PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"\nID=debian\n')
    write_file(root, "sys/class/thermal/thermal_zone0/temp", "48312\n")
    write_file(root, "sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", "1000000\n")
    write_file(root, "sys/class/net/wlan0/statistics/rx_bytes", "123456\n")
    write_file(root, "sys/class/net/wlan0/statistics/tx_bytes", "654321\n")
    write_file(root, "dist/build-id.txt", "abc1234-2026-10-15T12:00\n")
    return SystemSources(
        root=root,
        run_command=FakeCommands(),
        disk_usage=lambda path: DiskUsage(total=32_000_000_000, used=8_000_000_000, free=24_000_000_000),
        dist_dir=root / "dist",
    )


def test_a_pi_reports_its_board_and_system(tmp_path):
    system = read_bridge_system(fake_pi(tmp_path))

    assert system.hostname == "deq"
    assert system.model == "Raspberry Pi Zero 2 W Rev 1.0"
    assert system.operating_system == "Debian GNU/Linux 12 (bookworm)"
    assert system.kernel == "6.6.51+rpt-rpi-v8"
    assert system.cpu_count == 4


def test_a_pi_reports_its_load_heat_and_clock(tmp_path):
    system = read_bridge_system(fake_pi(tmp_path))

    assert system.uptime_seconds == 3600.5
    assert system.load_average == [0.12, 0.34, 0.56]
    assert system.cpu_temperature_celsius == 48.312
    assert system.cpu_frequency_mhz == 1000.0
    assert system.throttled_flags == "0x50000"


def test_a_pi_reports_memory_and_disk_in_bytes(tmp_path):
    system = read_bridge_system(fake_pi(tmp_path))

    assert system.memory_total_bytes == 425000 * 1024
    assert system.memory_available_bytes == 200000 * 1024
    assert system.swap_total_bytes == 102396 * 1024
    assert system.backend_memory_bytes == 51200 * 1024
    assert system.disk_total_bytes == 32_000_000_000
    assert system.disk_free_bytes == 24_000_000_000


def test_a_pi_reports_its_network_without_loopback(tmp_path):
    system = read_bridge_system(fake_pi(tmp_path))

    assert [interface.name for interface in system.interfaces] == ["wlan0"]
    wireless = system.interfaces[0]
    assert wireless.state == "UP"
    assert wireless.mac_address == "b8:27:eb:00:00:01"
    assert wireless.addresses == ["192.168.4.1/24"]
    assert wireless.received_bytes == 123456
    assert wireless.sent_bytes == 654321
    assert wireless.signal_dbm == -61.0


def test_a_pi_reports_the_frontend_build_it_serves(tmp_path):
    system = read_bridge_system(fake_pi(tmp_path))

    assert system.frontend_build == "abc1234-2026-10-15T12:00"


def test_an_empty_machine_answers_with_nothing_and_does_not_raise(tmp_path):
    """No procfs, no `ip`, no `vcgencmd`, no disk and no build: CI at worst."""

    def broken_disk_usage(path):
        raise OSError("no disk")

    sources = SystemSources(
        root=tmp_path,
        run_command=missing_command,
        disk_usage=broken_disk_usage,
        dist_dir=tmp_path / "dist",
    )

    system = read_bridge_system(sources)

    assert system.hostname is None
    assert system.memory_total_bytes is None
    assert system.disk_total_bytes is None
    assert system.throttled_flags is None
    assert system.frontend_build is None
    assert system.interfaces == []


def test_kibibyte_fields_skip_a_line_without_a_unit():
    values = parse_kibibyte_fields("MemTotal: 10 kB\nHugePages_Total: 0\n")

    assert values == {"MemTotal": 10240}


def test_os_release_without_a_pretty_name_is_unknown():
    assert parse_os_release("ID=debian\n") is None


def test_wireless_signals_skip_the_header_lines():
    text = "Inter-| sta-|   Quality\n face | tus | link level noise\n wlan0: 0000 70. -40. -256\n"

    assert parse_wireless_signals(text) == {"wlan0": -40.0}
