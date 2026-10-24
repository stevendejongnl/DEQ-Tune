#!/usr/bin/env python3
"""Lists, saves and forgets the Wi-Fi networks that the Pi joins.

The backend runs as the user `deq`, and NetworkManager needs root to
change a connection. So the backend calls this one script through sudo,
and the sudoers rule names this script and nothing else. The script takes
a fixed set of verbs and checks every argument. The backend never builds
an `nmcli` command line itself.

    deq-wifi-networks saved      the client networks, as JSON
    deq-wifi-networks visible    the networks in range, from the last scan
    deq-wifi-networks save SSID  reads the password on stdin, one line
    deq-wifi-networks forget SSID
    deq-wifi-networks join       asks deq-wifi-recover to run now
    deq-wifi-networks access-point      the access point's name, and whether
                                        it still uses the public default key
    deq-wifi-networks access-point-key  reads a new key on stdin, one line

The access point's key also comes on stdin. The helper writes it into the
access point's keyfile and never prints it. The new key applies the next
time the access point starts, at the next boot: a restart of the access
point now would drop the phone that asked for the change.

The password comes on stdin and goes into a keyfile that only root can
read. It never goes on a command line, because every user on the Pi can
read the command line of every process.

`save` and `forget` change saved settings only. They join nothing.
`deq-wifi-recover` joins a saved network that is in range, on its timer or
after `join`. NetworkManager can also join a saved network on its own,
the same as for a network saved by hand.

**Never touch the radio during a DEQ session.** A change to the radio
under the USB link has wedged the USB controller before. Two actions here
change the radio: `forget` of the network that the Pi uses now, and
`join`. Both refuse while the DEQ holds the link.

An exit code of 2 means a refusal, and stderr says why in words for a
person. Any other failure exits 1.

Install:
    sudo install -m 755 deq_wifi_networks.py /usr/local/bin/deq-wifi-networks
    echo 'deq ALL=(root) NOPASSWD: /usr/local/bin/deq-wifi-networks' \
        | sudo tee /etc/sudoers.d/030-deq-wifi-networks
    sudo chmod 440 /etc/sudoers.d/030-deq-wifi-networks
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

CLIENT_INTERFACE = "wlan0"
KEYFILE_DIRECTORY = Path("/etc/NetworkManager/system-connections")
UDC_DIRECTORY = Path("/sys/class/udc")
RECOVER_SERVICE = "deq-wifi-recover.service"
REFUSAL_EXIT_CODE = 2
SSID_MAXIMUM_BYTES = 32
HEX_KEY_PATTERN = re.compile(r"[0-9a-fA-F]{64}")
ACCESS_POINT_CONNECTION = "deq-tune-ap"
# configure-access-point.sh sets this key when it gets none. It is public, so
# the app asks the person to change it.
DEFAULT_ACCESS_POINT_KEY = "deq-tune-bridge"
PSK_LINE_PATTERN = re.compile(r"^psk=.*$", re.MULTILINE)


class Refusal(Exception):
    """A request that this script will not do. The message is for a person."""


def nmcli(*arguments: str) -> str:
    completed = subprocess.run(
        ["nmcli", *arguments], capture_output=True, text=True, check=True, timeout=20
    )
    return completed.stdout


def split_terse_line(line: str) -> list[str]:
    """Splits one line of `nmcli -t` output into its fields.

    nmcli writes a colon inside a value as `\\:` and a backslash as `\\\\`.
    An SSID can hold both, so a plain split on `:` breaks it.
    """
    fields: list[str] = []
    current: list[str] = []
    characters = iter(line)
    for character in characters:
        if character == "\\":
            current.append(next(characters, ""))
        elif character == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(character)
    fields.append("".join(current))
    return fields


def deq_session_is_running() -> bool:
    """Tells whether the DEQ holds the USB link now.

    `deq-accessory.service` stays active with no DEQ attached, because its
    main loop waits for the next session. So the service state says
    nothing. The USB controller's state does: it reads `not attached`
    while no DEQ is on the cable.
    """
    for controller in UDC_DIRECTORY.iterdir():
        state = (controller / "state").read_text().strip()
        if state != "not attached":
            return True
    return False


def client_connections() -> list[dict[str, str]]:
    """Every saved Wi-Fi connection that joins a network.

    The access point is a saved Wi-Fi connection too, so this skips each
    connection in `ap` mode.
    """
    connections = []
    for line in nmcli("-t", "-f", "UUID,TYPE,DEVICE", "connection", "show").splitlines():
        connection_uuid, connection_type, device = split_terse_line(line)
        if connection_type != "802-11-wireless":
            continue
        mode = nmcli("-g", "802-11-wireless.mode", "connection", "show", connection_uuid).strip()
        if mode == "ap":
            continue
        ssid = nmcli("-g", "802-11-wireless.ssid", "connection", "show", connection_uuid).strip()
        connections.append({"uuid": connection_uuid, "ssid": ssid, "device": device})
    return connections


def list_saved() -> list[dict[str, object]]:
    by_ssid: dict[str, bool] = {}
    for connection in client_connections():
        connected = connection["device"] == CLIENT_INTERFACE
        by_ssid[connection["ssid"]] = by_ssid.get(connection["ssid"], False) or connected
    return [{"ssid": ssid, "connected": connected} for ssid, connected in sorted(by_ssid.items())]


def list_visible() -> list[dict[str, object]]:
    """The networks in range, from the last scan.

    `--rescan no` reads the scan that NetworkManager holds already, so this
    does not touch the radio.
    """
    output = nmcli(
        "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list",
        "ifname", CLIENT_INTERFACE, "--rescan", "no",
    )
    strongest: dict[str, dict[str, object]] = {}
    for line in output.splitlines():
        ssid, signal_text, security = split_terse_line(line)
        if not ssid:
            continue
        signal = int(signal_text or 0)
        if ssid not in strongest or signal > int(strongest[ssid]["signal"]):
            strongest[ssid] = {"ssid": ssid, "signal": signal, "secured": security not in ("", "--")}
    return sorted(strongest.values(), key=lambda network: -int(network["signal"]))


def check_ssid(ssid: str) -> None:
    if not 1 <= len(ssid.encode()) <= SSID_MAXIMUM_BYTES:
        raise Refusal(f"A network name has 1 to {SSID_MAXIMUM_BYTES} bytes.")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in ssid):
        raise Refusal("A network name cannot hold control characters.")


def check_password(password: str) -> None:
    if password == "" or HEX_KEY_PATTERN.fullmatch(password):
        return
    if not 8 <= len(password) <= 63:
        raise Refusal("A Wi-Fi password has 8 to 63 characters.")
    if any(not 0x20 <= ord(character) <= 0x7E for character in password):
        raise Refusal("A Wi-Fi password holds printable ASCII characters only.")


def keyfile_string(value: str) -> str:
    """Escapes a value for a GLib keyfile, the format of a `.nmconnection` file.

    GLib drops a leading space and reads a backslash as an escape, so this
    writes both as escapes.
    """
    return value.replace("\\", "\\\\").replace(" ", "\\s")


def keyfile_text(ssid: str, password: str, connection_uuid: str) -> str:
    # The SSID goes in as a list of byte values. NetworkManager reads that
    # form for any SSID, so no character in it needs an escape.
    ssid_bytes = "".join(f"{byte};" for byte in ssid.encode())
    lines = [
        "[connection]",
        f"id={keyfile_string(ssid)}",
        f"uuid={connection_uuid}",
        "type=wifi",
        f"interface-name={CLIENT_INTERFACE}",
        "autoconnect=true",
        "",
        "[wifi]",
        "mode=infrastructure",
        # 2 turns Wi-Fi powersave off, as on every network saved by hand.
        # With it on, the Pi drops off the network while idle.
        "powersave=2",
        f"ssid={ssid_bytes}",
        "",
    ]
    if password:
        lines += ["[wifi-security]", "key-mgmt=wpa-psk", f"psk={keyfile_string(password)}", ""]
    lines += ["[ipv4]", "method=auto", "", "[ipv6]", "method=auto", ""]
    return "\n".join(lines)


def refuse_radio_change_during_session(action: str) -> None:
    if deq_session_is_running():
        raise Refusal(f"The DEQ is connected, so the Pi cannot {action} now. Try again when the car is off.")


def delete_connections(connections: list[dict[str, str]]) -> None:
    if any(connection["device"] == CLIENT_INTERFACE for connection in connections):
        refuse_radio_change_during_session("leave the network it uses")
    for connection in connections:
        nmcli("connection", "delete", connection["uuid"])


def save(ssid: str, password: str) -> None:
    """Saves a network, and replaces a saved network with the same name."""
    check_ssid(ssid)
    check_password(password)
    delete_connections([connection for connection in client_connections() if connection["ssid"] == ssid])
    connection_uuid = str(uuid.uuid4())
    path = KEYFILE_DIRECTORY / f"deq-{connection_uuid}.nmconnection"
    # Create the file with mode 600 before the password goes in. NetworkManager
    # also refuses a keyfile that other users can read.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(keyfile_text(ssid, password, connection_uuid))
    nmcli("connection", "load", str(path))


def forget(ssid: str) -> None:
    connections = [connection for connection in client_connections() if connection["ssid"] == ssid]
    if not connections:
        raise Refusal(f"The Pi has no saved network named {ssid}.")
    delete_connections(connections)


def join() -> None:
    refuse_radio_change_during_session("join a network")
    subprocess.run(["systemctl", "start", "--no-block", RECOVER_SERVICE], check=True, timeout=20)


def access_point_keyfile() -> Path | None:
    for line in nmcli("-t", "-f", "NAME,FILENAME", "connection", "show").splitlines():
        name, filename = split_terse_line(line)
        if name == ACCESS_POINT_CONNECTION:
            return Path(filename)
    return None


def read_access_point() -> dict[str, object] | None:
    """The access point's name, and whether its key is the public default.

    It never returns the key itself: the API that shows this answers anyone
    in Bluetooth range.
    """
    if access_point_keyfile() is None:
        return None
    ssid = nmcli("-g", "802-11-wireless.ssid", "connection", "show", ACCESS_POINT_CONNECTION).strip()
    key = nmcli("-s", "-g", "802-11-wireless-security.psk", "connection", "show", ACCESS_POINT_CONNECTION)
    return {"ssid": ssid, "uses_default_key": key.strip() == DEFAULT_ACCESS_POINT_KEY}


def keyfile_with_key(text: str, key: str) -> str:
    """Replaces the one `psk=` line of a keyfile. The key goes through
    `keyfile_string`, and a lambda, so no character in it reads as a
    regular-expression escape."""
    replaced, count = PSK_LINE_PATTERN.subn(lambda match: f"psk={keyfile_string(key)}", text)
    if count != 1:
        raise Refusal("The access point's settings hold no key to replace.")
    return replaced


def set_access_point_key(key: str) -> None:
    """Writes a new key into the access point's keyfile, for its next start."""
    if key == "":
        raise Refusal("The access point needs a password.")
    check_password(key)
    path = access_point_keyfile()
    if path is None:
        raise Refusal("The Pi has no access point. Run configure-access-point.sh first.")
    text = keyfile_with_key(path.read_text(), key)
    # A new file with mode 600, then one rename, so the keyfile is never half
    # written and never readable by other users.
    temporary = path.with_name(path.name + ".new")
    temporary.unlink(missing_ok=True)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(text)
    os.replace(temporary, path)
    nmcli("connection", "load", str(path))


def run(arguments: list[str]) -> object:
    match arguments:
        case ["saved"]:
            return list_saved()
        case ["visible"]:
            return list_visible()
        case ["save", ssid]:
            save(ssid, sys.stdin.readline().rstrip("\n"))
            return list_saved()
        case ["forget", ssid]:
            forget(ssid)
            return list_saved()
        case ["join"]:
            join()
            return None
        case ["access-point"]:
            return read_access_point()
        case ["access-point-key"]:
            set_access_point_key(sys.stdin.readline().rstrip("\n"))
            return read_access_point()
    raise Refusal("Use one of: saved, visible, save SSID, forget SSID, join, access-point, access-point-key.")


def main() -> int:
    try:
        print(json.dumps(run(sys.argv[1:])))
    except Refusal as refusal:
        print(refusal, file=sys.stderr)
        return REFUSAL_EXIT_CODE
    except subprocess.CalledProcessError as failure:
        print((failure.stderr or str(failure)).strip(), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
