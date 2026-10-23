#!/usr/bin/env bash
#
# Adds a Wi-Fi access point to the Pi, next to its client connection.
#
# A car has no home network in range, so the phone must join the Pi
# directly. The access point and the client link run together, so adding
# this does not take the home network away: SSH over the home network
# keeps working during an access point session.
#
# Two things make that work. Both came out the hard way on
# 2026-10-08. Keep them.
#
# **The access point needs an interface of its own.** Bound to `wlan0`
# it does not run beside the client link: NetworkManager replaces the
# client connection with it, because one device holds one connection. So
# this creates `ap0` with `iw dev wlan0 interface add ap0 type __ap`.
#
# **The access point must sit on the channel the client already uses.**
# The radio allows one channel for both interfaces. Left to choose, the
# access point takes a different one. The client then cannot
# re-associate, and NetworkManager gives up with reason `no-secrets`.
# That message is misleading, because the secrets are fine. So this reads
# the client's channel and pins the access point to it.
#
# That pinning is why the channel is not a fixed value here. It follows
# the client link, and it has to be read again whenever that link moves.
# So `connection.autoconnect` stays off. At boot there is no client link
# yet, and no channel to follow. `deq-access-point.sh` owns the
# bring-up at boot. It waits for a client link and falls back to channel 6.
#
# `ipv4.method shared` makes NetworkManager run the DHCP server and the
# NAT itself, so this needs no hostapd and no dnsmasq of its own.
# The Pi has neither installed, and it must stay that way.
#
# The key has a fixed default, so a phone can always join with nothing
# to look up. That default is in this file, so it is a convenience and
# not a secret. Pass a key as the first argument for an install that
# needs a real one. Either way the Pi keeps the key, and
# `nmcli -s -g` reads it back.
#
# Run it on the Pi, from this directory:
#   ./configure-access-point.sh
#
# Or give it a key of your own:
#   ./configure-access-point.sh "<key>"
#
# It creates the connection, starts it, and reports what answers.
# Running it again replaces the key, which is how a key gets rotated.

set -euo pipefail

connection_name="deq-tune-ap"
access_point_ssid="deq-tune"
access_point_address="192.168.4.1/24"
backend_port="8420"

# The key has a fixed default, and that is a deliberate trade.
#
# In a car there is no terminal to look a key up with, so a key nobody
# can recall is a key nobody can join with. The default is the same on
# every install, so a phone always gets on.
#
# What that costs: the default is in this public repository, so anybody
# who reads it can join an access point that still uses it. The access
# point reaches the API that drives the unit and nothing else. It reaches
# no car network and no internet, and the radio covers a few parking
# spaces. Change the key for an install that leaves the bench.
#
# Pass a key to use that instead, which is the right move for an
# install that leaves the bench:
#   ./configure-access-point.sh "my own key"
default_access_point_key="deq-tune-bridge"

if [ "$#" -gt 0 ]; then
    access_point_key="$1"
    key_source="the key given on the command line"
else
    access_point_key="${default_access_point_key}"
    key_source="the default key"
fi

if [ "${#access_point_key}" -lt 8 ]; then
    echo "A WPA key must have 8 characters or more." >&2
    exit 1
fi
if [ "${#access_point_key}" -gt 63 ]; then
    echo "A WPA key must have 63 characters or fewer." >&2
    exit 1
fi

# The access point has to follow the channel of the client link, and
# this reads it from the radio rather than from `nmcli dev wifi list`.
# That list leaves the IN-USE column blank on this Pi, so matching on it
# returns every channel in range and the first line wins by accident.
client_channel="$(/usr/sbin/iw dev wlan0 info 2>/dev/null \
    | sed -n -e 's/^[[:space:]]*channel \([0-9]\{1,\}\).*/\1/p' | head -1)"

if [ -z "${client_channel}" ]; then
    echo "No client link is up, so there is no channel to follow." >&2
    echo "Join a network first, then run this again." >&2
    exit 1
fi
echo "The client link uses channel ${client_channel}."

if nmcli -t -f NAME con show | grep -qx "${connection_name}"; then
    echo "The connection ${connection_name} exists already. Deleting it first."
    sudo nmcli con delete "${connection_name}" >/dev/null
fi

if ! /usr/sbin/iw dev | grep -q "Interface ap0"; then
    sudo /usr/sbin/iw dev wlan0 interface add ap0 type __ap
    echo "Created the ap0 interface."
fi

sudo nmcli con add type wifi ifname ap0 \
    con-name "${connection_name}" \
    ssid "${access_point_ssid}" >/dev/null

sudo nmcli con modify "${connection_name}" \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    802-11-wireless.channel "${client_channel}" \
    802-11-wireless.hidden no \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.proto rsn \
    wifi-sec.pairwise ccmp \
    wifi-sec.group ccmp \
    wifi-sec.psk "${access_point_key}" \
    ipv4.method shared \
    ipv4.addresses "${access_point_address}" \
    ipv6.method ignore \
    connection.autoconnect no

sudo nmcli con up "${connection_name}" >/dev/null
sleep 5

echo ""
echo "Active connections, which must show both ap0 and wlan0:"
nmcli -t -f NAME,DEVICE,ACTIVE con show --active

echo ""
echo "The access point:"
sudo /usr/sbin/iw dev ap0 info | grep -E "ssid|type|channel"

echo ""
echo "The DHCP server NetworkManager runs for it:"
pgrep -a dnsmasq | grep -o "dhcp-range=[^ ]*" || echo "No DHCP server is running."

echo ""
echo "The backend, asked at the address of the access point:"
curl -s --max-time 5 "http://${access_point_address%/*}:${backend_port}/api/device" \
    || echo "The backend did not answer."
echo ""

cat <<NEXT

The access point is up and the client link is still up.
It uses ${key_source}.

    network   ${access_point_ssid}
    password  ${access_point_key}

The Pi keeps the key, so it reads back at any time:

  sudo nmcli -s -g 802-11-wireless-security.psk con show ${connection_name}

A phone joins "${access_point_ssid}" and reaches the backend at
http://${access_point_address%/*}:${backend_port} .

Stop it:
  sudo nmcli con down ${connection_name}

Start it again, only while a client link is up, because the channel
comes from that link:
  sudo nmcli con up ${connection_name}

It does not come back by itself after a reboot. autoconnect is off,
because at boot there is no client link yet and so no channel to follow.
NEXT
