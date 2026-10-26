# The Pi side

A Raspberry Pi Zero 2 W in the car holds the USB link to the Pioneer DEQ
unit. The DEQ is a USB host, and it asks for an Android Open Accessory
(AOA). So the Pi plays an Android phone: its USB port runs as a gadget
that answers the accessory handshake. The gadget relays whole frames to
the backend (`backend/`) over a Unix socket, and the backend drives the
unit.

The phone reaches the Pi over Wi-Fi at the bench, and over Bluetooth Low
Energy in the car. Wireless Android Auto holds the phone's Wi-Fi in the
car, so the car app carries the REST API over BLE.

## The pieces

| File | What it does | Where it runs from |
|---|---|---|
| `deq_accessory.py`, `deq-accessory.service` | The USB gadget: AOA handshake, audio function, frame relay | `/home/deq/deq_accessory.py` |
| `f_accessory/` | The Android kernel's accessory driver, vendored | built on the Pi, `make && sudo make install` |
| `f_uac1_deq/` | A UAC1 audio driver with the descriptors of a real tablet | built on the Pi |
| `deq-backend.service` | The backend, from `backend/` | `/home/deq/deq-tune/backend` |
| `deq_ble_bridge.py`, `deq-ble-bridge.service` | The REST API over BLE GATT, for the car app | `/usr/local/bin/` |
| `deq-access-point.sh`, `.service`, `configure-access-point.sh` | A Wi-Fi access point beside the client link | `/usr/local/bin/` |
| `deq_portal.py`, `deq-portal.service`, `deq-portal-dns.conf` | A captive portal that opens the app on a phone | `/usr/local/bin/` |
| `deq_wifi_networks.py` | The root helper behind the web app's Wi-Fi dialog | `/usr/local/bin/deq-wifi-networks` |
| `deq-wifi-recover.sh`, `.service`, `.timer` | Brings a lost client link back | `/usr/local/bin/` |
| `deq-heartbeat.sh`, `deq-session-record.sh` | Plain log files that outlive a brown-out | `/usr/local/bin/` |
| `deq_updater.py`, `deq-updater.service`, `.timer` | Installs each new release by itself, every 30 minutes | `/usr/local/bin/` |
| `deq-tune.avahi.service` | Announces the web app as `_deq-tune._tcp` on port 8420, so a phone finds the Pi by name | `/etc/avahi/services/deq-tune.service` |

The Pi has no RTC, so journald throws its journal away when NTP sets the
clock. The heartbeat writes `/var/log/deq-heartbeat.log` once a minute,
and the session recorder writes each change of `/api/device` to
`/var/log/deq-session.log`.

The backend service runs `uv run --no-sync`, because the car has no route
to the internet. The database is `/home/deq/deq.db`, outside the code
tree, so a new backend keeps the profiles.

## Updates

`deq_updater.py` runs from `deq-updater.timer` every 30 minutes, as root.
It asks GitHub for the latest release, and writes what it found to
`/home/deq/deq-update-state.json`.

- With automatic updates on (the default), it downloads
  `deq-tune-<version>.tar.gz`, checks its SHA-256, unpacks it into
  `/home/deq/deq-tune.next`, and runs `uv sync --frozen` there as `deq`,
  which fills uv's cache. Then it swaps the trees, keeps the old one as
  `/home/deq/deq-tune.prev`, builds `.venv` again in the live tree from the
  cache (`--offline`), restarts the backend, and waits up to 60 seconds
  for `/health`. A virtualenv records its absolute path in its scripts, so
  one built in the staging tree fails after the rename. A backend
  that does not answer gets the old tree back.
- It installs a changed gadget only while no DEQ session is live. Until
  then the state file says `gadget_pending`.
- `{"automatic": false}` in `/home/deq/deq-update-settings.json` switches
  automatic updates off. A run then only reports the new version. The file
  `/home/deq/deq-update-request` asks for one update anyway.
- With no internet, as in the car, a run changes nothing.

The web app's settings page shows this state and writes the settings and
request files. Its Update button also starts the updater at once, through
one sudoers rule: `deq ALL=(root) NOPASSWD: /usr/bin/systemctl start
--no-block deq-updater.service`. Without the rule, the request waits for the
next timer run.

The release workflow builds the tarball and attaches it with its
checksum. The updater updates the backend tree, the web app and the
gadget. It does not update the systemd units or the files in
`/usr/local/bin/`.

## What a reimplementation must get right

Four bugs, each paid for with a car session.

**Open with `0x00`, and give it its 24-byte body.** Captured app traffic
starts mid-session with `0x02`, so a copy of a capture gets the opening
command wrong. Without the body, the unit answers STATUS -5 in 40 ms and
then ignores every frame.

**Put the accessory interface at index 2.** configfs numbers interfaces
in link order. A real tablet's audio function has two interfaces, so
audio takes 0 and 1 and the accessory lands on 2. At 0 the link died
after 1.4 to 6 seconds. `AUDIO_FIRST` relinks so audio comes first.
Leave it True.

**Make the audio function a source.** `f_uac1` names its attributes from
the gadget's view:

| configfs | ALSA node | direction |
|---|---|---|
| `p_chmask 3`, `c_chmask 0` | `pcm0p`, playback | gadget to host, right |
| `c_chmask 3`, `p_chmask 0` | `pcm0c`, capture | host to gadget, wrong |

**Make a feed that dies say so.** The gadget checks its audio feed on
each keepalive and logs "this session is NOT feeding audio" when it dies.

These did not matter, each measured against a real DEQ: the startup
burst's content, the transaction ids, the app's timing, the keepalive
cadence, a running audio stream, and the audio descriptors. Dropping the
audio function does matter: an accessory-only `0x2D00` device gets no
`SET_CONFIGURATION` at all.

## The flags at the top of `deq_accessory.py`

Each flag has its reason beside it in the file. Leave `AUDIO_FIRST` and
`WITH_AUDIO` True, and `SEND_BURST` False. `RELAY_TO_BACKEND` hands the
link to the backend. While a backend holds the socket, the gadget sends
nothing of its own. When the backend detaches, the gadget takes the link
back with a keepalive, so a backend restart keeps the DEQ session.

`MAX_SPEED` is the bus speed the gadget offers, `"high-speed"` by
default. `"full-speed"` exists for one test: the ESP32-S3 is full speed
only, and the DEQ drops it after it reads the configuration descriptor
(see `esp-gadget/README.md`). The test asked whether the DEQ drops the
Pi at full speed too. It does. On 2026-10-26, at full speed, the kernel
log showed `new device is full-speed` and `new address 1`, and then
nothing: no accessory handshake, and the DEQ in its error state. At high
speed the handshake came within a second. Before the handshake, the
gadget log shows each change of the controller's state and speed (`USB
state: addressed, speed full-speed`). The state log polls, so a host
that drops the device within a poll can leave no line there. `dmesg`
shows each enumeration.

`build_frame` repeats the backend's encoder, because the Pi runs this one
file with no backend beside it. `backend/app/test_pi_gadget_encoder.py`
checks that the two still give the same bytes.

## Traps

- **A gadget restart ends a live DEQ session.** The DEQ enumerates the
  new gadget within a second and handshakes again, with no replug
  (measured twice on 2026-10-26). An older gadget wedged the USB
  controller here (`dwc2_hsotg_txfifo_flush: timeout`) until the DEQ was
  power cycled. A backend restart keeps the session.
- **Do not add a network function to the gadget.** Extra interfaces
  change the interface numbering, and the DEQ depends on it. The USB port
  is not a way in.
- **The Pi dies with the car.** It takes power from the DEQ, so the car
  going to sleep browns it out.
- **The gadget log holds NUL bytes.** Read it with `grep -a`.
- **The access point needs its own interface (`ap0`) and the client
  link's channel.** On another channel the client cannot re-associate,
  and NetworkManager reports a misleading `no-secrets`.
- **The access point's default key is public.** It is `deq-tune-bridge`,
  in `configure-access-point.sh`. Pass a key of your own for an install
  that leaves the bench, or set one in the app: Settings → Wi-Fi → The
  Pi's access point. The app also asks for one at its first start while
  the default key is in use. `deq-wifi-networks access-point-key` writes it into
  the keyfile, and restarts the Pi 5 seconds later so the key applies. A reboot
  is safe during a DEQ session (measured 2026-10-24: the DEQ handshakes again,
  as after a replug). The API
  says only whether the key is the default, never the key.
- **The BLE bridge needs no pairing yet.** Any device nearby can reach the
  API through it.
- **The BLE bridge forgets a half-received request when a client
  subscribes or goes.** A request that lost its last chunk stayed in the
  buffer before, and the next client's first request failed to parse.

## Playing our own audio

The unit plays whatever `SourceMode` it holds, set by `0x0b`. THROUGH
plays the car's own audio and needs `0x1a` PLAY_READY after it, or the
car stays silent. CAR_SOURCE plays the car's audio through the DSP.
SP_OTHER_SOURCE (5) plays what the gadget writes to its audio function.
Set `FEED_AUDIO` and `AUDIO_FEED_TONE_HZ` to hear a tone through the car's
speakers on mode 5.

## Changing a driver

Pipe the directory over, build it on the Pi, and load it with the
service stopped and the gadget unbound, between sessions:

    tar -czf /tmp/f_uac1_deq.tgz -C pi-gadget f_uac1_deq
    ssh deq@<pi> 'cat > /home/deq/f.tgz' < /tmp/f_uac1_deq.tgz
    ssh deq@<pi> 'cd /home/deq && rm -rf f_uac1_deq && mkdir f_uac1_deq \
        && tar -xzf f.tgz -C f_uac1_deq --strip-components=1 \
        && cd f_uac1_deq && make && sudo make install'

Compare `md5sum` on both ends. `scp` to this Pi produced zero-byte and
spliced files.
