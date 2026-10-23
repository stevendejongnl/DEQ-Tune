# `usb_f_accessory` for the Raspberry Pi

Android's accessory gadget function, built as an out-of-tree module so a
Pi can be the Android device a Pioneer DEQ expects to talk to.

## Why this is here

Android's accessory support is not a set of USB descriptors. It is this
driver. It owns the bulk endpoints, answers the AOA control requests,
re-enumerates the device into accessory mode, and exposes
`/dev/usb_accessory`. An app only opens that character device and reads
and writes it. Everything that holds the link up happens here, beneath
the app.

An earlier `pi-gadget/deq_aoa_ffs.py`, now removed, reimplemented this in
Python over FunctionFS. The DEQ configured the device, and its LED turned
blue, but it got no further. Every bulk read failed with `EBADMSG`, and the unit
dropped the link after about three seconds. Running the real driver
removes the reimplementation.

The driver is Android-only. Mainline Linux never merged it, so no
distribution kernel ships it.

## Where the source came from

| | |
|---|---|
| Project | Android common kernel, `android.googlesource.com/kernel/common` |
| Branch | `android14-6.1` |
| Files | `drivers/usb/gadget/function/f_accessory.c`, `include/uapi/linux/usb/f_accessory.h` |
| Retrieved | 2026-10-06 |
| Licence | GPL-2.0, Copyright (C) 2011 Google, Inc., Mike Lockwood |

The history pages on that host need a sign-in, so the branch name and the
retrieval date stand in for a commit hash.

`f_accessory.c` includes `<linux/usb/f_accessory.h>`, so this directory
keeps the UAPI header at `include/linux/usb/f_accessory.h`. The `Makefile` puts
`include/` on the include path.

Keep each local change to the vendored source small and obvious, so the
diff against upstream stays readable. A comment marks each change and
says what it adapts and why.

## Building

On the Pi:

    cd pi-gadget/f_accessory
    make DEBUG=1
    sudo make DEBUG=1 install
    sudo modprobe usb_f_accessory

The module on the Pi has `DEBUG=1`. A plain build compiles out every
message, because this kernel has `CONFIG_DYNAMIC_DEBUG` off. Those
messages found the interface-number bug.

Check that configfs sees the function type. A loaded module does not
prove that:

    sudo mkdir /sys/kernel/config/usb_gadget/deqtune/functions/accessory.deq

If that `mkdir` fails, the module is not providing the function, and a
symlink to a directory that nobody created leaves a dangling link in
the configuration. The gadget still binds and the host still sends
ENABLE, but every endpoint then breaks. The earlier `uac1` mistake
showed these same symptoms.

## One thing the driver does not do

It defines only `0x2D00` (accessory) and `0x2D01` (accessory + ADB). It
does not set `0x2D04` (accessory + audio). On Android, the userspace gadget layer
selects the product id from the set of enabled functions. This driver
does not, so the Python side must select `0x2D04`.
That matters here: the DEQ asks for audio with `SET_AUDIO_MODE` value 1,
and an accessory-only device receives no ENABLE from it at all.
