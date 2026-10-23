#!/bin/sh
# Records what the backend made of each DEQ session, outside journald.
#
# A session without the engine lasts about two minutes, and the Pi takes
# power from the DEQ, so it browns out when the car sleeps. `/api/device`
# is a live query: ask it after the car sleeps and the answer is gone. So
# this asks while the session runs and writes every change to disk.
#
# It writes only on a change, not every poll. A session that worked is
# then three or four lines, and a whole file is readable at a glance.
#
# The reason the Pi needs this at all is the same as the heartbeat's: no
# RTC, so journald throws its persistent journal away when NTP corrects
# the clock. Read this file, not `journalctl`.
LOG=/var/log/deq-session.log
DEVICE_URL=http://localhost:8420/api/device
POLL_SECONDS=2

note() {
    printf '%s up=%ss %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" \
        "$(cut -d' ' -f1 /proc/uptime)" "$1" >> "$LOG"
}

trap 'note "stopping (asked to)"; exit 0' TERM INT

note "starting"
previous=""
while true; do
    # --max-time keeps a hung backend from stalling the poll loop.
    current=$(curl -s --max-time 3 "$DEVICE_URL" 2>/dev/null)
    if [ -z "$current" ]; then
        current="no answer from the backend"
    fi
    if [ "$current" != "$previous" ]; then
        note "$current"
        previous="$current"
    fi
    sleep "$POLL_SECONDS"
done
