#!/bin/sh
# Writes one line a minute, so you can tell the causes of a reboot apart.
#
# The Pi has no RTC. journald sees the clock jump backwards when NTP
# corrects it, logs "Time jumped backwards, rotating", and throws its
# persistent journal away. So journald loses the last moments before a
# reboot, and you cannot tell a power cut from a reset.
#
# This writes outside journald. Each line carries the seconds since boot,
# which no clock correction can disturb, so the file says how far the Pi
# got. A line reading "stopping" means something asked it to go down. A
# file that stops mid-run means the power went away.
LOG=/var/log/deq-heartbeat.log

note() {
    printf '%s up=%ss %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" \
        "$(cut -d' ' -f1 /proc/uptime)" "$1" >> "$LOG"
}

trap 'note "stopping (asked to)"; exit 0' TERM INT

note "starting"
while true; do
    note "alive volts=$(vcgencmd measure_volts core 2>/dev/null | cut -d= -f2) throttled=$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)"
    sleep 60
done
