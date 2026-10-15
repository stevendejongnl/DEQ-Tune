"""The bridge's machine statistics: memory, disk, network, load and the rest.

`bridge_health.py` answers one question: is the Pi well? This module answers
the questions that come after it. How full is the card? Which address does
the Pi have on which network? How warm is it? Which frontend build does it
serve?

Every value comes from procfs, sysfs, `/etc/os-release`, `ip -j addr` and
`vcgencmd`. The module needs no extra package. Each reader returns `None`
where the machine cannot say, and nothing here may raise. A laptop or a CI
runner has no `vcgencmd` and no Pi model, and the report must still answer.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.bridge_health import read_throttled_flags
from app.paths import BUILD_ID_FILE_NAME, DIST_DIR

IP_COMMAND_TIMEOUT_SECONDS = 5.0

# /proc/meminfo gives sizes in kibibytes.
BYTES_PER_KIBIBYTE = 1024


@dataclass(frozen=True)
class SystemSources:
    """Where the readers look. A test points each one at a fake.

    `root` is the file system root. A test passes a directory that holds
    a hand-written `proc/meminfo` and the rest.
    """

    root: Path = Path("/")
    run_command: Callable = subprocess.run
    disk_usage: Callable = shutil.disk_usage
    dist_dir: Path = DIST_DIR


@dataclass(frozen=True)
class NetworkInterface:
    name: str
    state: str
    mac_address: str | None = None
    addresses: list[str] = field(default_factory=list)
    received_bytes: int | None = None
    sent_bytes: int | None = None
    signal_dbm: float | None = None


@dataclass(frozen=True)
class BridgeSystem:
    hostname: str | None = None
    model: str | None = None
    operating_system: str | None = None
    kernel: str | None = None
    architecture: str | None = None
    python_version: str | None = None
    uptime_seconds: float | None = None
    load_average: list[float] | None = None
    cpu_count: int | None = None
    cpu_temperature_celsius: float | None = None
    cpu_frequency_mhz: float | None = None
    throttled_flags: str | None = None
    memory_total_bytes: int | None = None
    memory_available_bytes: int | None = None
    swap_total_bytes: int | None = None
    swap_free_bytes: int | None = None
    backend_memory_bytes: int | None = None
    disk_total_bytes: int | None = None
    disk_free_bytes: int | None = None
    frontend_build: str | None = None
    interfaces: list[NetworkInterface] = field(default_factory=list)


def read_text(path: Path) -> str | None:
    """Returns the file's text without the trailing whitespace, or None."""
    try:
        return path.read_text(errors="replace").strip()
    except Exception:
        return None


def parse_kibibyte_fields(text: str) -> dict[str, int]:
    """Turns `Name:  1234 kB` lines into a map of byte counts.

    /proc/meminfo and /proc/self/status both use this format.
    """
    values: dict[str, int] = {}
    for line in text.splitlines():
        name, _, rest = line.partition(":")
        parts = rest.split()
        if len(parts) == 2 and parts[1] == "kB" and parts[0].isdigit():
            values[name.strip()] = int(parts[0]) * BYTES_PER_KIBIBYTE
    return values


def parse_os_release(text: str) -> str | None:
    """Returns `PRETTY_NAME` from /etc/os-release."""
    for line in text.splitlines():
        key, _, value = line.partition("=")
        if key == "PRETTY_NAME":
            return value.strip().strip('"') or None
    return None


def parse_load_average(text: str) -> list[float] | None:
    try:
        return [float(value) for value in text.split()[:3]]
    except ValueError:
        return None


def parse_wireless_signals(text: str) -> dict[str, float]:
    """Returns the signal level in dBm per interface, from /proc/net/wireless.

    The two header lines have no colon after a name, so the parser skips them.
    """
    signals: dict[str, float] = {}
    for line in text.splitlines():
        name, separator, rest = line.partition(":")
        columns = rest.split()
        if not separator or len(columns) < 3:
            continue
        try:
            signals[name.strip()] = float(columns[2].rstrip("."))
        except ValueError:
            continue
    return signals


def parse_ip_addresses(output: str) -> list[dict]:
    """Returns the interfaces from the JSON of `ip -j addr`."""
    try:
        interfaces = json.loads(output)
    except ValueError:
        return []
    return interfaces if isinstance(interfaces, list) else []


def read_ip_addresses(sources: SystemSources) -> list[dict]:
    try:
        completed = sources.run_command(
            ["ip", "-j", "addr"],
            capture_output=True,
            text=True,
            timeout=IP_COMMAND_TIMEOUT_SECONDS,
        )
    except Exception:
        return []
    return parse_ip_addresses(completed.stdout or "")


def read_interface_counter(sources: SystemSources, name: str, counter: str) -> int | None:
    text = read_text(sources.root / "sys/class/net" / name / "statistics" / counter)
    return int(text) if text is not None and text.isdigit() else None


def read_interfaces(sources: SystemSources) -> list[NetworkInterface]:
    """Returns every network interface except loopback."""
    signals = parse_wireless_signals(read_text(sources.root / "proc/net/wireless") or "")
    interfaces = []
    for entry in read_ip_addresses(sources):
        name = entry.get("ifname")
        if not isinstance(name, str) or name == "lo":
            continue
        interfaces.append(
            NetworkInterface(
                name=name,
                state=str(entry.get("operstate", "UNKNOWN")),
                mac_address=entry.get("address"),
                addresses=[
                    f"{address['local']}/{address['prefixlen']}"
                    for address in entry.get("addr_info", [])
                    if "local" in address and "prefixlen" in address
                ],
                received_bytes=read_interface_counter(sources, name, "rx_bytes"),
                sent_bytes=read_interface_counter(sources, name, "tx_bytes"),
                signal_dbm=signals.get(name),
            )
        )
    return interfaces


def read_cpu_temperature_celsius(sources: SystemSources) -> float | None:
    """Returns the first thermal zone, in °C. The kernel gives millidegrees."""
    text = read_text(sources.root / "sys/class/thermal/thermal_zone0/temp")
    try:
        return int(text) / 1000 if text is not None else None
    except ValueError:
        return None


def read_cpu_frequency_mhz(sources: SystemSources) -> float | None:
    """Returns the current frequency of the first core. The kernel gives kHz."""
    text = read_text(sources.root / "sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
    try:
        return int(text) / 1000 if text is not None else None
    except ValueError:
        return None


def read_cpu_count(sources: SystemSources) -> int | None:
    text = read_text(sources.root / "proc/cpuinfo")
    if text is None:
        return None
    count = sum(1 for line in text.splitlines() if line.startswith("processor"))
    return count or None


def read_model(sources: SystemSources) -> str | None:
    """Returns the board name, such as `Raspberry Pi Zero 2 W Rev 1.0`.

    The device tree ends the string with a NUL byte.
    """
    text = read_text(sources.root / "proc/device-tree/model")
    if text is None:
        return None
    return text.rstrip("\x00") or None


def read_uptime_seconds(sources: SystemSources) -> float | None:
    text = read_text(sources.root / "proc/uptime")
    try:
        return float(text.split()[0]) if text else None
    except ValueError:
        return None


def read_throttled_hex(sources: SystemSources) -> str | None:
    flags = read_throttled_flags(sources.run_command)
    return None if flags is None else f"0x{flags:x}"


def read_disk(sources: SystemSources) -> tuple[int | None, int | None]:
    try:
        usage = sources.disk_usage(sources.root)
    except Exception:
        return None, None
    return usage.total, usage.free


def read_bridge_system(sources: SystemSources | None = None) -> BridgeSystem:
    """Returns everything this machine can say about itself."""
    sources = sources or SystemSources()
    memory = parse_kibibyte_fields(read_text(sources.root / "proc/meminfo") or "")
    process = parse_kibibyte_fields(read_text(sources.root / "proc/self/status") or "")
    disk_total, disk_free = read_disk(sources)
    load_text = read_text(sources.root / "proc/loadavg")
    return BridgeSystem(
        hostname=read_text(sources.root / "proc/sys/kernel/hostname"),
        model=read_model(sources),
        operating_system=parse_os_release(read_text(sources.root / "etc/os-release") or ""),
        kernel=read_text(sources.root / "proc/sys/kernel/osrelease"),
        architecture=platform.machine() or None,
        python_version=platform.python_version(),
        uptime_seconds=read_uptime_seconds(sources),
        load_average=parse_load_average(load_text) if load_text else None,
        cpu_count=read_cpu_count(sources),
        cpu_temperature_celsius=read_cpu_temperature_celsius(sources),
        cpu_frequency_mhz=read_cpu_frequency_mhz(sources),
        throttled_flags=read_throttled_hex(sources),
        memory_total_bytes=memory.get("MemTotal"),
        memory_available_bytes=memory.get("MemAvailable"),
        swap_total_bytes=memory.get("SwapTotal"),
        swap_free_bytes=memory.get("SwapFree"),
        backend_memory_bytes=process.get("VmRSS"),
        disk_total_bytes=disk_total,
        disk_free_bytes=disk_free,
        frontend_build=read_text(sources.dist_dir / BUILD_ID_FILE_NAME) or None,
        interfaces=read_interfaces(sources),
    )
