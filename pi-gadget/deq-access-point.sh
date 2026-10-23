#!/usr/bin/env bash
#
# Brings the DEQ access point up, at boot and after a reset.
#
# Two things stop a plain `nmcli con up deq-tune-ap` from working at
# boot, and this script exists for both.
#
# `ap0` is a runtime interface. `iw dev wlan0 interface add` creates it,
# and a reboot destroys it, so the connection has no device to bind to
# and activation fails with "mismatching interface name". This creates
# the interface first.
#
# The radio runs one channel for both interfaces, so the access point
# has to sit on the channel the client link already uses. At boot there
# may be no client link yet: in a car no known network is in range, and
# at the bench the home network needs a few seconds to associate. So
# this waits a short while for a client link, follows its channel when
# one appears, and falls back to a fixed channel when none does. The
# fallback is safe in that case, because nothing else holds the radio.
#
# The DEQ link must not be disturbed. `deq-accessory.service` holds a
# fragile USB link, and reconfiguring the radio while a session runs has
# wedged the USB controller before. So this runs once at boot, before a
# session is likely, and never restarts itself.

set -euo pipefail

connection_name="deq-tune-ap"
access_point_interface="ap0"
radio_interface="wlan0"
fallback_channel="6"
regulatory_domain="NL"
seconds_to_wait_for_client="30"

log() {
    printf 'deq-access-point: %s\n' "$1"
}

# Prints the channel of the associated client link. Prints nothing when
# the client is not associated.
#
# This reads the radio. It avoids `nmcli dev wifi list`, which leaves the
# IN-USE column blank on this Pi. So a `^\*` match returns every
# channel in range instead of the one in use, and the first line wins by
# accident. The same SSID also appears on more than one channel here, so
# matching by name is ambiguous too. `iw dev wlan0 info` reports the
# channel the interface is on, and prints no channel line at
# all when it is not associated.
channel_of_client_link() {
    /usr/sbin/iw dev "${radio_interface}" info 2>/dev/null \
        | sed -n -e 's/^[[:space:]]*channel \([0-9]\{1,\}\).*/\1/p' | head -1
}

wait_for_client_channel() {
    local waited=0
    local channel=""

    while [ "${waited}" -lt "${seconds_to_wait_for_client}" ]; do
        channel="$(channel_of_client_link)"
        if [ -n "${channel}" ]; then
            printf '%s' "${channel}"
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
    done
    return 1
}

# The kernel's regulatory domain does not survive a reboot. NetworkManager
# does not read `wpa_supplicant.conf`, which holds the country. So the
# domain comes up as `00`, the world-wide fallback, which caps transmit
# power at 6 dBm. The access point still works at that power, but only
# just. So set the real domain before bringing it up.
if [ "$(/usr/sbin/iw reg get | sed -n -e 's/^country \([A-Z0-9]*\).*/\1/p' | head -1)" = "00" ]; then
    /usr/sbin/iw reg set "${regulatory_domain}"
    log "set the regulatory domain to ${regulatory_domain}"
fi

if ! nmcli -t -f NAME con show | grep -qx "${connection_name}"; then
    log "the connection ${connection_name} does not exist, so there is nothing to bring up"
    log "run pi-gadget/configure-access-point.sh on the Pi first"
    exit 0
fi

if /usr/sbin/iw dev | grep -q "Interface ${access_point_interface}"; then
    log "${access_point_interface} exists already"
else
    /usr/sbin/iw dev "${radio_interface}" interface add \
        "${access_point_interface}" type __ap
    log "created ${access_point_interface}"
fi

if access_point_channel="$(wait_for_client_channel)"; then
    log "a client link uses channel ${access_point_channel}, so the access point follows it"
else
    access_point_channel="${fallback_channel}"
    log "no client link appeared, so the access point uses channel ${access_point_channel}"
fi

nmcli con modify "${connection_name}" \
    802-11-wireless.channel "${access_point_channel}"

nmcli con up "${connection_name}" >/dev/null
log "the access point is up on channel ${access_point_channel}"
