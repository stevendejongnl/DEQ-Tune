#!/usr/bin/env bash
#
# Gets the Pi's client Wi-Fi link back after NetworkManager gives up.
#
# NetworkManager stops retrying a connection after enough failures, and
# then nothing brings it back. On 2026-10-09 a Wi-Fi glitch took the home
# network away for a moment. The access point survived on `ap0`, but the
# client link on `wlan0` did not. The Pi was off the network until
# somebody power cycled it. Nothing on the Pi was going to fix that,
# because `deq-access-point.service` is `Type=oneshot` and runs only at
# boot. This runs every fifteen minutes instead (see the timer).
#
# Three rules decide what this script can do.
#
# **Never touch the radio during a DEQ session.** `deq-accessory.service`
# holds a fragile USB link, and reconfiguring the radio under it has
# wedged the USB controller before. The same reason
# `deq-access-point.service` carries no `Restart=`. If the DEQ is on the
# cable, this exits and waits for the next run. The USB controller's state
# says so. The state of `deq-accessory.service` does not: the service stays
# active with no DEQ attached, because its main loop waits for the next
# session. Until 2026-10-14 this script read the service state, so it
# refused every run.
#
# **Never trade the access point away for a client link.** In a car the
# access point is the main purpose, and no known network is in range. So
# if the radio sees no saved network, this does nothing at all. A missing
# client link is the normal state there, not a fault.
#
# **The access point follows the client's channel, so recovery may have
# to move it.** One radio serves both interfaces on one channel. If the
# client cannot associate while the access point holds a channel the
# target network does not use, the access point blocks it. So this
# drops the access point, lets the client associate, reads the channel
# it landed on, and brings the access point back up pinned to it. Only
# in that case does the access point go down, and it comes back in the
# same run.
#
# Install:
#   sudo install -m 755 deq-wifi-recover.sh /usr/local/bin/
#   sudo install -m 644 deq-wifi-recover.service deq-wifi-recover.timer \
#       /etc/systemd/system/
#   sudo systemctl daemon-reload
#   sudo systemctl enable --now deq-wifi-recover.timer

set -euo pipefail

connection_name="deq-tune-ap"
access_point_interface="ap0"
radio_interface="wlan0"
seconds_to_wait_for_association="25"

log() {
    printf 'deq-wifi-recover: %s\n' "$1"
}

# Reads the radio rather than `nmcli dev wifi list`, for the reason
# deq-access-point.sh gives: the IN-USE column is blank on this Pi, and
# the same SSID appears on more than one channel, so both of the obvious
# matches return the wrong answer. `iw dev <iface> info` prints no
# channel line at all when the interface is not associated.
channel_of_interface() {
    /usr/sbin/iw dev "$1" info 2>/dev/null \
        | sed -n -e 's/^[[:space:]]*channel \([0-9]\{1,\}\).*/\1/p' | head -1
}

channel_of_client_link() {
    channel_of_interface "${radio_interface}"
}

channel_of_access_point() {
    channel_of_interface "${access_point_interface}"
}

client_link_is_up() {
    [ -n "$(channel_of_client_link)" ]
}

# Reads `not attached` on every USB controller while no DEQ is on the
# cable.
deq_session_is_running() {
    local state_file
    for state_file in /sys/class/udc/*/state; do
        [ -r "${state_file}" ] || continue
        if [ "$(cat "${state_file}")" != "not attached" ]; then
            return 0
        fi
    done
    return 1
}

access_point_is_up() {
    nmcli -t -f NAME con show --active | grep -qx "${connection_name}"
}

# Every saved Wi-Fi connection that joins a network, as opposed to
# serving one. The access point is itself a saved Wi-Fi connection, so
# filtering by type alone would include it and this would try to "join"
# the Pi's own network.
saved_client_connections() {
    local name mode
    nmcli -t -f NAME,TYPE con show \
        | awk -F: '$2 == "802-11-wireless" { print $1 }' \
        | while IFS= read -r name; do
            mode="$(nmcli -g 802-11-wireless.mode con show "${name}" 2>/dev/null || true)"
            [ "${mode}" = "ap" ] || printf '%s\n' "${name}"
        done
}

ssid_of_connection() {
    nmcli -g 802-11-wireless.ssid con show "$1" 2>/dev/null || true
}

# Prints the name of the first saved client connection whose network the
# radio can see. Nothing in range means a car, not a fault.
connection_in_range() {
    local visible name ssid
    visible="$(nmcli -t -f SSID dev wifi list ifname "${radio_interface}" --rescan yes 2>/dev/null || true)"
    [ -n "${visible}" ] || return 1
    while IFS= read -r name; do
        [ -n "${name}" ] || continue
        ssid="$(ssid_of_connection "${name}")"
        [ -n "${ssid}" ] || continue
        if printf '%s\n' "${visible}" | grep -qxF "${ssid}"; then
            printf '%s\n' "${name}"
            return 0
        fi
    done < <(saved_client_connections)
    return 1
}

await_association() {
    local waited=0
    while [ "${waited}" -lt "${seconds_to_wait_for_association}" ]; do
        if client_link_is_up; then
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
    done
    return 1
}

# Pins the access point to a channel and brings it up. Creating `ap0`
# first matters after a reboot, when the interface no longer exists, and
# is harmless when it does.
raise_access_point_on_channel() {
    local channel="$1"
    if ! /usr/sbin/iw dev | grep -q "Interface ${access_point_interface}"; then
        /usr/sbin/iw dev "${radio_interface}" interface add \
            "${access_point_interface}" type __ap
    fi
    nmcli con modify "${connection_name}" 802-11-wireless.channel "${channel}"
    nmcli con up "${connection_name}" >/dev/null
    log "the access point is up on channel ${channel}"
}

# The access point's configured channel, which is not always the channel
# it is running on. A later `con up` uses the configured value.
configured_access_point_channel() {
    nmcli -g 802-11-wireless.channel con show "${connection_name}" 2>/dev/null || true
}

main() {
    if deq_session_is_running; then
        log "a DEQ session is running, so the radio stays untouched"
        return 0
    fi

    if ! nmcli -t -f NAME con show | grep -qx "${connection_name}"; then
        log "no ${connection_name} connection exists, so there is nothing to reconcile"
        return 0
    fi

    if client_link_is_up; then
        local client_channel access_point_channel configured
        client_channel="$(channel_of_client_link)"

        if ! access_point_is_up; then
            log "the client link is up but the access point is not, bringing it up"
            raise_access_point_on_channel "${client_channel}"
            return 0
        fi

        # Compare the channels the two interfaces are *running* on, not the
        # access point's saved value. The radio co-locates them by itself:
        # when the home network roamed from channel 6 to 10, `ap0` followed
        # with no help from anything here. Comparing against the saved value
        # instead reports a mismatch every time the home network roams. The
        # fix for that is an access point bounce, which drops any phone on
        # the access point. Measured on 2026-10-09, where the saved
        # value said 6 while both interfaces were already on 10 together.
        access_point_channel="$(channel_of_access_point)"
        if [ -n "${access_point_channel}" ] \
            && [ "${access_point_channel}" != "${client_channel}" ]; then
            log "the interfaces disagree (ap0 ${access_point_channel}, client ${client_channel}), re-pinning"
            nmcli con down "${connection_name}" >/dev/null || true
            raise_access_point_on_channel "${client_channel}"
            return 0
        fi

        # The running channels agree, so nothing is wrong now. The saved
        # value can still be stale, and it is what a later `con up` uses at
        # boot before any client link exists. Write it back without a
        # bounce, because this changes no running interface.
        configured="$(configured_access_point_channel)"
        if [ "${configured}" != "${client_channel}" ]; then
            nmcli con modify "${connection_name}" \
                802-11-wireless.channel "${client_channel}"
            log "refreshed the saved channel to ${client_channel} without touching the radio"
        fi
        return 0
    fi

    local target
    if ! target="$(connection_in_range)"; then
        log "no saved network is in range, so this is a car and not a fault"
        return 0
    fi
    log "the client link is down and ${target} is in range, trying it"

    if nmcli con up "${target}" >/dev/null 2>&1 && await_association; then
        log "the client link is back on channel $(channel_of_client_link)"
        return 0
    fi

    if ! access_point_is_up; then
        log "could not join ${target}, and the access point is not what is blocking it"
        return 1
    fi

    # Last resort, and the case that cost a power cycle: the access point
    # holds the radio on a channel the target network does not use, so the
    # client can never associate. Give the radio back, join, then pin the
    # access point to wherever the client landed.
    log "dropping the access point so the client can pick its own channel"
    nmcli con down "${connection_name}" >/dev/null || true
    nmcli con up "${target}" >/dev/null 2>&1 || true

    if await_association; then
        local recovered
        recovered="$(channel_of_client_link)"
        log "the client link is back on channel ${recovered}"
        raise_access_point_on_channel "${recovered}"
        return 0
    fi

    # The client still did not come up, so put the access point back the
    # way it was rather than leaving the Pi with neither.
    log "could not join ${target} even with the radio free, restoring the access point"
    raise_access_point_on_channel "$(configured_access_point_channel)"
    return 1
}

main "$@"
