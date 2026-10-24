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

Each stage, the frame counts, the DEQ's strings and the longest link go
into flash (NVS). The next boot prints the report on the COM port, so a car
session needs no laptop: plug the COM cable in at home and read it.

    REPORT boot=9 last_stage=7(hold) best_stage=7(hold) held_s=72
    REPORT host="laptop" model="fake-deq-host" audio_mode=1 unhandled_request=0
    REPORT sync_status=0 replies_ok=18 refused=0 last_refusal=0 on 0x00 notifications=0
    REPORT unanswered_keepalives=15

`held_s` counts from the first frame to the last answered keepalive. A
keepalive with no reply in two seconds adds one to `unanswered_keepalives`
and does not extend `held_s`. So a DEQ that goes quiet does not look like a
held link.

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

## The desk test

A laptop is a USB host, like the DEQ. `fake_deq_host.py` takes the DEQ's
side of stages 1 to 6 against the board's USB port, and answers every frame
with STATUS 0. Run it with the backend's environment, which has the codec:

    cd backend && uv run --extra usb python ../esp-gadget/fake_deq_host.py --seconds 110

`--answer-seconds 75` stops the answers after 75 seconds and keeps reading,
as a DEQ that goes quiet.

Measured on 2026-10-24: every stage passed. The board came back as
`18d1:2d04` with interfaces 0 and 1 audio and 2 the accessory, sent the
whole cold start, and kept up a keepalive every nine seconds. The laptop
took the audio function as a sound card and recorded two seconds of the
stream at the full rate (352,246 of 352,800 bytes). A run with
`--seconds 110 --answer-seconds 75` gave the report above: stage 7 at 72
seconds, then each later keepalive counted as unanswered.

So the desk proves the board's side. Only a car session can show the real
DEQ's side: whether it configures the accessory (stage 5) and answers
(stages 6 and 7).

## Tests

`backend/app/test_esp_gadget_frame.py` compiles `main/deq_frame.c` with the
laptop's C compiler and checks it against the backend's encoder and decoder,
with five replies captured from a real unit.
