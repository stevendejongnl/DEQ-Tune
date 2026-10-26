"""Reads the probe's boot records from the board's COM port.

It resets the board through the COM port's RTS line, so the board prints
the records of the earlier boots first, and shows the REPORT lines. Run
it with ESP-IDF's Python, which has pyserial:

    . $IDF_PATH/export.sh
    python esp-gadget/read_records.py /dev/ttyACM0

`--all` shows the whole log of the new boot, not only the records.
"""

import argparse
import re
import sys
import time

import serial

COLOUR_CODES = re.compile(r"\x1b\[[0-9;]*m")
LOG_PREFIX = re.compile(r"^[IWE] \(\d+\) probe: ")


def reset_board(port) -> None:
    # DTR stays high, so the board boots its firmware and not the loader.
    port.dtr = False
    port.rts = True
    time.sleep(0.1)
    port.rts = False


def read_lines(port, seconds: float):
    buffer = ""
    give_up = time.monotonic() + seconds
    while time.monotonic() < give_up:
        buffer += port.read(4096).decode(errors="replace")
        *lines, buffer = buffer.split("\n")
        yield from lines
    if buffer:
        yield buffer


def main() -> int:
    arguments = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    arguments.add_argument("port", help="the COM port, for example /dev/ttyACM0")
    arguments.add_argument("--seconds", type=float, default=4.0, help="how long to read after the reset")
    arguments.add_argument("--all", action="store_true", help="show every line, not only the records")
    options = arguments.parse_args()

    with serial.Serial(options.port, 115200, timeout=0.2) as port:
        reset_board(port)
        for line in read_lines(port, options.seconds):
            line = COLOUR_CODES.sub("", line).rstrip("\r")
            if options.all:
                print(line)
            elif "REPORT" in line:
                print(LOG_PREFIX.sub("", line))
    return 0


if __name__ == "__main__":
    sys.exit(main())
