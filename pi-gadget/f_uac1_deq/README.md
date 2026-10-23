# `usb_f_uac1_deq` for the Raspberry Pi

The kernel's UAC1 gadget function, vendored and changed so the audio
descriptors match the SM-T560 tablet's. The Pioneer DEQ answers that
tablet, so the descriptors it sends are the reference.

## Why this is here

The DEQ once completed the AOA handshake with the Pi and then sent
nothing back. This driver came from the search for that cause. The
cause was the opening frame, not the descriptors (see `../README.md`).
The repo keeps the matched descriptors, because they rule out a whole
class of doubt.

Comparing the stock `f_uac1` with Android's own `f_audio_source.c` found
differences in the audio function. Configfs removes some of them on
the stock driver, and `deq_accessory.py` does that. It turns off the mute
and volume controls, which also removes the AudioControl interrupt
endpoint. It sets `req_number` to 4, the tablet's count. Three
differences need the driver itself:

| Difference | Tablet | Stock `f_uac1` |
|---|---|---|
| ISO IN `wMaxPacketSize` | 256 | 200, a literal in `u_uac1.h` that does not follow the sample rate |
| The feature unit | present, with no control in it | either present with controls, or absent |
| `bInCollection` | 2, naming AudioControl and AudioStreaming | 1, naming only AudioStreaming |

The feature unit is the awkward one. Turning the controls off through
configfs removes the unit, which shortens the AudioControl block by one
descriptor and makes the output terminal read from the input terminal
directly. The tablet keeps the unit and offers no control. Neither stock
shape is the tablet's.

`bInCollection` was found by measuring this driver's output, not by
reading the source: the UAC1 spec means that collection to list the
streaming interfaces an AudioControl interface owns, so upstream follows
the spec and the tablet does not.

## The three local changes

A comment in the source marks each change and says what it adapts and
why. Two are new configfs attributes, both off by default. So this
driver behaves like upstream until a setting tells it otherwise.

| Change | Attribute | Default |
|---|---|---|
| ISO IN `wMaxPacketSize` 256 | none, it is unconditional | none |
| Keep the feature unit with no control | `p_fu_empty` | 0 |
| List AudioControl in `baInterfaceNr` | `ac_in_collection` | 0 |

The driver ignores `p_fu_empty` when `p_mute_present` or `p_volume_present` is
set. A real control needs a `bmaControls` entry, so the unit cannot be
empty.

Only the full-speed and high-speed ISO IN descriptor carries 256. The
SuperSpeed one keeps the upstream value, because this Pi's `dwc2`
controller is high speed and never sends it.

## It does not replace the stock driver

The module registers the configfs function type `uac1deq`, not `uac1`, so
it loads beside the in-tree `usb_f_uac1`. To go back to the stock
driver, set `AUDIO_FUNCTION_TYPE = "uac1"` in `deq_accessory.py` and
restart the service. You do not have to uninstall anything, and the service skips the two new
settings by itself.

## Where the source came from

| | |
|---|---|
| Project | `github.com/raspberrypi/linux` |
| Tag | `stable_20260911` |
| Files | `drivers/usb/gadget/function/f_uac1.c`, `u_uac1.h`, `u_audio.h`, `uac_common.h` |
| Retrieved | 2026-10-07 |
| Licence | GPL-2.0+, Copyright (C) 2016 Ruslan Bilovol, (C) 2021 Julian Scheel |

`stable_20260911` is the tag that matches the running kernel,
`6.18.50+rpt-rpi-v8`, built from Debian `1:6.18.50-1+rpt1` on 2026-09-11.

This directory renames `f_uac1.c` to `f_uac1_deq.c`, so a reader cannot mistake it for
the stock driver. The three headers are private kernel headers that the
`linux-headers` package does not install, so this directory carries its
own copies and the `Makefile` finds them beside the source.

**The headers must match the running kernel.** `u_audio.h` describes a
struct this module passes to the kernel's own `u_audio` module. A copy
from another version would disagree about its layout, and the module
would load and then corrupt memory rather than fail.

This driver links against `u_audio`, which the kernel ships separately.
Every symbol it needs is `EXPORT_SYMBOL_GPL`, so the build needs no in-tree
source to link against it.

## Building

On the Pi:

    cd pi-gadget/f_uac1_deq
    make
    sudo make install
    sudo modprobe usb_f_uac1_deq

Check that configfs sees the function type. A loaded module does not
prove that:

    sudo mkdir /sys/kernel/config/usb_gadget/deqtune/functions/uac1deq.test
    ls /sys/kernel/config/usb_gadget/deqtune/functions/uac1deq.test
    sudo rmdir /sys/kernel/config/usb_gadget/deqtune/functions/uac1deq.test

That listing must contain `p_fu_empty` and `ac_in_collection`. If it does
not, the stock driver answered and this module is not loaded.

## The module on the Pi

The module went onto the Pi on 2026-10-07, built and installed:

| | |
|---|---|
| Path | `/lib/modules/6.18.50+rpt-rpi-v8/extra/usb_f_uac1_deq.ko` |
| md5 | `5ede6ce2c4860f8d034af7cf59e94184` |

The Pi does not keep the build directory. To change the driver, pipe
this directory over and build it there. `../README.md` has the commands.

## The descriptor check

Reasoning about descriptors let the first three differences go
unnoticed. So the check below measures this build and does not trust it.

A temporary `pr_err` loop over `f_audio_desc[]`, just before
`usb_assign_descriptors`, prints every descriptor as bytes. Bind a
throwaway gadget to the UDC and read them out of `dmesg`. The
committed source does not hold that instrumentation. Add it, measure, and take
it out again.

**Do this only when the Pi has no DEQ on its USB port.** Binding a test gadget needs the
real one unbound, and unbinding a live link wedges the USB controller
until the unit is power cycled. Check `dmesg` for `acc_function_enable`
and the log's `+seconds` column first.

Measured output, with `p_fu_empty` and `ac_in_collection` both 1:

    09 04 00 00 00 01 01 00 01           AC interface
    0a 24 01 00 01 28 00 02 00 01        AC header, wTotalLength 40, bInCollection 2, {0,1}
    0c 24 02 01 01 02 00 02 03 00 06 05  input terminal, id 1, MICROPHONE, 2 channels
    09 24 03 02 01 01 00 03 07           output terminal, id 2, STREAMING, source 3
    09 24 06 03 01 02 00 00 00           feature unit, id 3, source 1, no control set
    09 04 01 00 00 01 02 00 0c           AS interface, alt 0, no endpoint
    09 04 01 01 01 01 02 00 0d           AS interface, alt 1, one endpoint
    07 24 01 02 01 01 00                 AS header, PCM
    0b 24 02 01 02 02 10 01 44 ac 00     type I format, 2 channels, 16 bit, 44100 Hz
    09 05 81 05 00 01 04 00 00           ISO IN endpoint, 0x81, wMaxPacketSize 256
    07 25 01 01 00 00 00                 class-specific ISO endpoint

Every descriptor is now the tablet's length, and the AudioControl block
is 40 bytes like the tablet's. There is no AudioControl interrupt
endpoint, which the tablet also lacks.

**Three small differences remain, and none is a length.** This list
records them. Then nobody who measures them again thinks they are new:

- **The two sides number the terminals and the unit in a different order.**
  This driver numbers the input terminal 1, the output terminal 2 and the
  feature unit 3. The tablet numbers them 1, 3 and 2. The graph is the same
  either way: input terminal to feature unit to output terminal. A UAC1 id is
  an arbitrary label that only has to be consistent inside the block.
- **`wLockDelay`** is 0 here and 1 on the tablet, in the
  class-specific ISO endpoint descriptor.
- **The string indices differ**, because this driver names its terminals
  and the tablet does not.

Whether any of those matters is a question for the DEQ, not for the
source. The lengths and the topology are what this change set out to fix.
