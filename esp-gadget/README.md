# The ESP32-S3 gadget

An ESP32-S3 in the Pi's place on the DEQ's USB port. The board costs a
fraction of a Pi. This directory holds the **link probe**: firmware that
answers the DEQ's accessory handshake the way `pi-gadget/` does, holds a
conversation, and records how far it got.

The probe proves the USB link only. The backend (profiles, the EQ maths,
the API) is Python and runs on the Pi. An ESP-only setup needs that logic
somewhere else, which is a separate decision.

## The board

An ESP32-S3-DevKitC-1 with the ESP32-S3-WROOM-1-N16R8 module and two USB-C
ports:

| Port | Job |
|---|---|
| **USB** (the chip's USB-OTG) | the link: into the DEQ's USB-A port in the car, or into a laptop for the desk test |
| **COM** (a CH343 serial chip) | flashing and the live log |

The RGB LED sits on GPIO 48 (board v1.0). A v1.1 board has it on GPIO 38:
set `PROBE_LED_GPIO` with `idf.py menuconfig`. The probe runs without the
LED when the pin is wrong.

## What the probe checks

It walks the stages a working link takes, and the LED shows the stage
reached:

| # | Stage | LED |
|---|---|---|
| 0 | waiting for a host | dim blue |
| 1 | a host is on the bus | blue |
| 2 | `GET_PROTOCOL` arrived, answered 2 | purple |
| 3 | six identification strings and `SET_AUDIO_MODE` | magenta |
| 4 | `START`, and the board came back as `18d1:2d04` | orange |
| 5 | the host configured the accessory | yellow |
| 6 | `COMMAND_SYNC` drew a reply with STATUS 0 | teal |
| 7 | keepalives held the link for 60 seconds | green |

Red means the DEQ refused a frame with a STATUS other than 0.

It sends what `pi-gadget/deq_accessory.py` sends on its own: `COMMAND_SYNC`
with the app's 24 bytes, the read-only cold start (`0x21 0x17 0x15 0x03 0x04
0x0a 0x20 0x09 0x06`) and a keepalive (`0x02`) every nine seconds. It
writes nothing to the unit's settings.

It copies the three things the DEQ requires, which the Pi found (see
`deq_usb_device.h`):

1. AOA protocol version 2.
2. Answers to the AOA requests before the device is configured.
3. An audio function, with the accessory at interface 2 behind the
   AudioControl and AudioStreaming interfaces: the SM-T560's shape, UAC1, a
   microphone terminal, a feature unit with no controls, and a 256-byte
   isochronous IN endpoint at 44100 Hz. The probe streams silence.

## The report

Each boot keeps its own record in flash (NVS), for the last eight boots.
The record holds the reset reason, how long the board stayed up, the stage
reached, the bus events, the DEQ's strings and the frame counts. Each boot
prints the earlier records on the COM port, oldest first. So a car session
needs no laptop: plug the COM cable in at home and read them. A car can
power the board up several times, and a later boot does not overwrite the
one that shows the problem.

Measured on the desk on 2026-10-25 (boot 17 is the desk test):

    REPORT boot=16 reset=poweron alive_s=647 stage=0(none) bus_at_ms=0 mounts=0 suspends=0 resumes=0 unmounts=0
    REPORT boot=17 reset=poweron alive_s=91 stage=6(sync) bus_at_ms=1047 mounts=2 suspends=1 resumes=0 unmounts=0
    REPORT   host="laptop" model="fake-deq-host" strings=6 audio_mode=1 unhandled_request=0
    REPORT   sync_status=0
    REPORT   held_s=18 replies_ok=12 refused=0 last_refusal=0 on 0x00 unanswered_keepalives=4 notifications=0
    REPORT this boot is 19

- `reset` tells a power loss (`poweron`, `brownout`) from a crash
  (`panic`, a watchdog).
- `alive_s` is the uptime at the last save. The board saves every ten
  seconds, so it is up to ten seconds short.
- `bus_at_ms` is the uptime when a host first showed up on the USB port.
- `trace` lists the first 32 bus events and SETUP packets in order. A
  SETUP packet shows as `bmRequestType bRequest:wValue:wIndex:wLength` in
  hex, so `8006:0200:0000:0020` is GET_DESCRIPTOR configuration, 32 bytes.
- `reads` counts the host's descriptor reads: the device descriptor, the
  configuration descriptor and the strings (`string_indexes` has bit n
  set for each string n read). They show where a host stops when it never
  configures the board. A desk run gives `device=4 configuration=6
  string=12 string_indexes=0x000f`.
- `mounts` counts each time the host configured the board, in tablet mode
  and in accessory mode. `suspends` counts the gaps in bus traffic. A
  re-enumeration after START gives one.
- `held_s` counts from the first frame to the last answered keepalive. A
  keepalive with no reply in two seconds adds one to
  `unanswered_keepalives` and does not extend `held_s`. So a DEQ that goes
  quiet does not look like a held link.

`host` and `model` are the first two strings the host sent. A real DEQ sends
`Pioneer` and a model such as `DEQ-1000A-MZ`. The desk test sends `laptop`.

## Build and flash

Needs ESP-IDF 5.3 or later for `esp32s3`. Measured with v5.3.1, esp_tinyusb
1.7.6 and TinyUSB 0.21.

    . $IDF_PATH/export.sh
    cd esp-gadget
    idf.py set-target esp32s3     # once per checkout
    idf.py build
    idf.py -p /dev/ttyACM0 flash  # the COM port
    idf.py -p /dev/ttyACM0 monitor

Opening the COM port resets the board, and the report comes first.
`read_records.py` resets the board and prints only the records:

    python esp-gadget/read_records.py /dev/ttyACM0

It needs pyserial, which ESP-IDF's Python has. (It replaces a scratch
script that read the records through 2026-10-25. Not yet run itself.)

## The desk test

A laptop is a USB host, like the DEQ. `fake_deq_host.py` takes the DEQ's
side of stages 1 to 6 against the board's USB port, and answers every frame
with STATUS 0. Run it with the backend's environment, which has the codec:

    cd backend && uv run --extra usb python ../esp-gadget/fake_deq_host.py --seconds 110

`--answer-seconds 75` stops the answers after 75 seconds and keeps reading,
as a DEQ that goes quiet. The script only takes a full-speed device. A
phone or tablet on the same laptop shows the same `18d1:4ee7`, but it runs
at high speed, so the script leaves it alone.

Measured on 2026-10-24: every stage passed. The board came back as
`18d1:2d04` with interfaces 0 and 1 audio and 2 the accessory, sent the
whole cold start, and kept up a keepalive every nine seconds. The laptop
took the audio function as a sound card and recorded two seconds of the
stream at the full rate (352,246 of 352,800 bytes). A run with
`--seconds 110 --answer-seconds 75` reached stage 7 at 72 seconds, and
each later keepalive counted as unanswered.

So the desk proves the board's side. Only a car session can show the real
DEQ's side: whether it configures the accessory (stage 5) and answers
(stages 6 and 7).

## The first car session (2026-10-24)

The board was on the DEQ's USB-A port with a plain USB-A to USB-C cable,
so the DEQ powered it. The DEQ showed its error at once. The board's old
report (one record, before the per-boot records) said: four boots, and the
last one reached stage 1 only. A host was on the bus, but no AOA request
came. The second session (2026-10-25), with the per-boot records, gave two
answers:

- On the DEQ's power alone, each boot lost power within about one second
  of the DEQ seeing the board (`alive_s=0`, `reset=poweron`, four tries).
  The DEQ's port cannot run the DevKit, and the DEQ flashes red.
- With the COM port on an external USB supply, the board stayed up. The
  DEQ showed up on the bus at 3.5 s, never configured the board
  (`mounts=0`) and suspended the bus.

So a car session needs the external supply, and the DEQ still stops
during enumeration.

The trace of the later sessions on 2026-10-25 shows where, the same each
time:

    RESET RESET  device(64)  RESET  SET_ADDRESS 1  device(18)
    configuration(9)  configuration(32)  SUSPEND

The DEQ reads the whole configuration descriptor and drops the board. It
reads no strings and sends no `SET_CONFIGURATION` and no `GET_PROTOCOL`.
Three configurations gave this same stop: the SM-T560's ADB interface
with 64-byte bulk endpoints, the same with 512, and the Pi's own shape
(the Android accessory interface 0xFF/0xFF/0x00, the strings "AOA" and
"Android Accessory Interface", 512-byte bulk). The firmware keeps the
Pi's shape. The one difference left from the Pi is the speed: the
ESP32-S3 is full speed only. Not proven yet.

## Tests

`backend/app/test_esp_gadget_frame.py` compiles `main/deq_frame.c` with the
laptop's C compiler and checks it against the backend's encoder and decoder,
with five replies captured from a real unit.
