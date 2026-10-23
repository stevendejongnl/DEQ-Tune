"""Runs the Pi as the Android device a Pioneer DEQ expects to talk to.

The kernel does the USB work. `usb_f_accessory`, built from the Android
common kernel in `f_accessory/`, owns the bulk endpoints, answers the AOA
control requests, and exposes `/dev/usb_accessory`. This program only
builds the gadget, waits for the DEQ to ask for accessory mode, switches
the gadget over, and then reads and writes that character device. Android
itself uses the same division of labour: there, the app only reads and
writes this device.

An earlier version of this file did all of that in Python over
FunctionFS. It got as far as the DEQ configuring the device, and no
further: every bulk read failed EBADMSG.

Run as root:
    sudo python3 deq_accessory.py
"""
import datetime
import errno
import fcntl
import os
import socket
import subprocess
import sys
import threading
import time

GADGET_ROOT = "/sys/kernel/config/usb_gadget/deqtune"
ACCESSORY_DEVICE = "/dev/usb_accessory"

# The SM-T560's own identity, read from a live `lsusb -v`. The SM-T560 is
# the one device known to complete this handshake with the DEQ, so the
# gadget copies it and does not invent an identity.
PRE_ACCESSORY_VENDOR_ID = 0x18D1
PRE_ACCESSORY_PRODUCT_ID = 0x4EE7
DEVICE_PROTOCOL = 0x01
MANUFACTURER = "SAMSUNG"
PRODUCT = "SAMSUNG_Android"
SERIAL_NUMBER = "0000000000000000"

# Google's accessory product ids say which functions the device offers:
# 0x2D00 accessory, 0x2D02 audio, 0x2D04 accessory + audio, and the odd
# ids add ADB. The SM-T560 that works with this DEQ reports 0x2D05
# (accessory + audio + ADB). This gadget has no ADB, so 0x2D04.
#
# The driver itself only defines 0x2D00 and 0x2D01. On Android the
# product id comes from the userspace gadget layer, not from the driver,
# so choosing 0x2D04 is this program's job. It matters: the DEQ asks for
# audio with SET_AUDIO_MODE, and an accessory-only device gets no
# SET_CONFIGURATION from it at all.
ACCESSORY_PRODUCT_ID = 0x2D04

# 0x2D00 is accessory with no audio function. Set WITH_AUDIO to False to
# re-enumerate as that instead.
#
# Leave it True. A test on 2026-10-06 presented the gadget to the DEQ as
# accessory-only, and the DEQ never configured the device at all: no
# SET_CONFIGURATION, no acc_function_set_alt, only acc_function_bind and
# then the handshake again. **An audio function is mandatory.**
#
# The function does not take the car's audio. The source mode decides what
# the unit plays. Measured by ear in a car on 2026-10-08:
#
#   mode 5 SP_OTHER_SOURCE, a 440 Hz tone  -> the tone plays
#   mode 4 THROUGH, same gadget, same feed -> the car's own audio plays
#
# The car stays silent until PLAY_READY (0x1a) follows the mode write. The
# real app ends every cold start with it, and the backend's connect does
# the same since 2026-10-12. Sent on its own in a car on 2026-10-11, it
# brought the audio back at once.
#
# The unit refuses a volume write with STATUS -6 while it holds THROUGH.
# It accepts one on mode 5 or 6. MIX_OTHER_SOURCE (6) is not yet heard in
# a car. See "Playing our own audio" in README.md.
#
# `SourceMode` in the APK (`model/b/v`) picks the unit's input. Its
# constructor is (name, ordinal, wireValue), so the wire value is one
# less than the ordinal. Read the third argument, not the second:
#
#   0 STAND_ALONE        1 SP_GENUINE_SOURCE   2 MIX_GENUINE_SOURCE
#   3 CAR_SOURCE         4 THROUGH             5 SP_OTHER_SOURCE
#   6 MIX_OTHER_SOURCE   7 SP_GENUINE_PURE_SOURCE
#   8 MIX_GENUINE_PURE_SOURCE
#
# COMMAND_MODE, 0x0b, carries the value. This program never sends it. The
# backend does. The real app plays the phone's own music library through
# the DEQ, and this gadget is a USB audio source in the same way. See
# "Playing our own audio" in README.md.
WITH_AUDIO = True
ACCESSORY_ONLY_PRODUCT_ID = 0x2D00

# What the audio function presents, copied from the SM-T560's own
# f_audio_source.c in the LineageOS kernel for that tablet
# (kernel/samsung/gtelwifinew, drivers/usb/gadget/function).
#
# Android's AOA audio is a SOURCE: audio flows device to host. Its
# descriptors say so: UAC_INPUT_TERMINAL_MICROPHONE, one ISO IN endpoint,
# 44100 Hz, 16-bit stereo. AUDIO_PLAYBACK_CHANNEL_MASK below says which
# f_uac1 attribute gives that direction.

# Which interface number the accessory function gets.
#
# **Leave this True. It is what makes the link hold.**
#
# configfs numbers interfaces in link order. This program links the
# accessory function when it builds the gadget, before the handshake. So
# without this setting, it is always interface 0.
#
# The SM-T560 is the other way around: Android's f_audio_source presents
# two interfaces, AudioControl and AudioStreaming, so audio takes 0 and 1
# and the accessory interface lands on 2.
#
# The DEQ looks for the accessory interface at index 2. With it at 0, the
# unit configured the device, addressed interface 2, and found no
# endpoints there. That caused the EAGAIN from usb_ep_queue on ep_in. The
# unit then gave up after one to six seconds. With it at 2 the link holds
# for as long as the DEQ has power.
#
# This relinks the accessory function inside enter_accessory_mode, which
# configfs allows only while the UDC is unbound.
AUDIO_FIRST = True

# Which way the audio flows, and this was wrong until 2026-10-07.
#
# The gadget must be a SOURCE: audio goes device to host, the Pi to the
# DEQ. The SM-T560's own f_audio_source.c says so. It declares
# UAC_INPUT_TERMINAL_MICROPHONE and `bEndpointAddress = USB_DIR_IN`. The
# DEQ is a car amplifier, so it expects to receive audio.
#
# In f_uac1 the names are the gadget's own view, not the host's, which is
# the trap. Measured on this kernel, with the function created and the
# card read from /proc/asound:
#
#   p_chmask 3, c_chmask 0  ->  pcm0p, playback  ->  gadget to host  (right)
#   c_chmask 3, p_chmask 0  ->  pcm0c, capture   ->  host to gadget  (wrong)
#
# This file set the second line until now, so the gadget asked the DEQ
# to send it audio. The tablet does the opposite. For the same reason,
# `aplay` found no device to write to: there was no playback node at all.
AUDIO_PLAYBACK_CHANNEL_MASK = "3"
AUDIO_SAMPLE_RATE = "44100"
AUDIO_SAMPLE_SIZE = "2"
AUDIO_CAPTURE_DISABLED = "0"

# The feature unit must carry no controls, the way the tablet's does.
#
# f_uac1 declares a mute control and a volume control by default, and it
# writes a bmaControls entry for every channel. Android's
# f_audio_source.c declares a feature unit with no controls at all.
#
# These four turn both controls off. That also removes the AudioControl
# interrupt endpoint, which the tablet does not have. On the stock driver
# it removes the feature unit as well. AUDIO_FEATURE_UNIT_EMPTY puts an
# empty one back. The descriptors did not cause the DEQ's early silence,
# but the match rules out a class of doubt.
AUDIO_CONTROL_ABSENT = "0"

# Which UAC1 driver to use, and so which descriptors the DEQ reads.
#
# "uac1deq" is the vendored driver in pi-gadget/f_uac1_deq. It exists for
# two descriptor differences that configfs cannot reach:
#
#   - the ISO IN endpoint carries 256 bytes, like the tablet's, not 200
#   - the feature unit stays in the AudioControl block with no control in
#     it, which is the tablet's shape. Turning the controls off on the
#     stock driver removes the unit instead
#
# "uac1" is the kernel's own driver. Both can be loaded at once, so this
# is the whole switch back: set it to "uac1", restart the service, and
# the stock descriptors return. AUDIO_FEATURE_UNIT_EMPTY is then ignored,
# because the stock driver has no such attribute.
#
# Build and install the vendored driver before setting this:
#
#     cd pi-gadget/f_uac1_deq && make && sudo make install
#
# The module name does not follow from the type. The vendored module is
# usb_f_uac1_deq and its type is uac1deq, so deriving one from the other
# gives usb_f_uac1deq, which modprobe does not find. Keep them separate.
AUDIO_FUNCTION_TYPE = "uac1deq"
AUDIO_MODULE_NAME = "usb_f_uac1_deq"
AUDIO_FUNCTION_NAME = f"{AUDIO_FUNCTION_TYPE}.deq"

# What to use for the kernel's own driver, if AUDIO_FUNCTION_TYPE goes
# back to "uac1": the module is then usb_f_uac1 and the type is uac1.

# Whether the feature unit stays, with no control in it.
#
# Only the vendored driver has this attribute. The tablet's
# f_audio_source.c puts a feature unit of UAC_DT_FEATURE_UNIT_SIZE(0)
# between its input and output terminal, so its AudioControl block has
# one descriptor the stock driver cannot produce: with the controls off,
# the stock driver drops the unit and the output terminal reads from the
# input terminal directly.
AUDIO_FEATURE_UNIT_EMPTY = "1"

# Whether the AudioControl interface lists itself in baInterfaceNr.
#
# Only the vendored driver has this attribute. The tablet sends
# bInCollection 2 and baInterfaceNr {0, 1}, which names the AudioControl
# interface and the AudioStreaming one. Upstream counts only streaming
# interfaces, so it sends bInCollection 1.
#
# The UAC1 spec is on upstream's side here. This setting reproduces the
# tablet, because Pioneer built the DEQ against the tablet.
AUDIO_CONTROL_IN_COLLECTION = "1"

# How many ISO requests the function queues.
#
# f_uac1 defaults to 2. Android's f_audio_source.c allocates 4
# (IN_EP_REQ_COUNT). The DEQ cannot see this number, because no
# descriptor holds it. So this is for the stream's own steadiness, not for
# the handshake.
AUDIO_REQUEST_COUNT = "4"

# From include/linux/usb/f_accessory.h. _IO('M', 7) and _IO('M', 8).
ACCESSORY_IS_START_REQUESTED = 0x4D07
ACCESSORY_GET_AUDIO_MODE = 0x4D08

# _IOW('M', 1..6, char[256]). These read back the six strings the DEQ
# sent during the handshake. The strings say what the unit thinks it is
# talking to, so they are worth logging once per session: one of them
# reads "Supported application is not installed" when the unit sees no
# app.
ACCESSORY_STRING_IOCTLS = (
    ("manufacturer", 0x41004D01),
    ("model", 0x41004D02),
    ("description", 0x41004D03),
    ("version", 0x41004D04),
    ("uri", 0x41004D05),
    ("serial", 0x41004D06),
)
ACCESSORY_STRING_LENGTH = 256

START_POLL_SECONDS = 0.2

# How long to keep trying the first write while the DEQ configures the
# re-enumerated device. It drops the link after about seven seconds if
# it is not satisfied, so there is no point waiting much beyond that.
ONLINE_WAIT_SECONDS = 6.0
ONLINE_POLL_SECONDS = 0.1

# How often to write a keepalive. Nine seconds is the real app's own gap.
#
# An older version used two seconds, to watch a link that died six
# seconds after its first frame. With the accessory interface at index 2
# the link holds for as long as the DEQ has power, so the app's gap wins.
KEEPALIVE_SECONDS = 9.0

# How long to wait for the reader thread to notice a dropped link.
READER_STOP_SECONDS = 5.0

# Which command opens the session, and the one experiment it exists for.
#
# COMMAND_KEEPALIVE (0x02) is what every capture shows, so it is the
# default and the safe answer. OPENING_COMMAND exists to test the one
# thing the captures cannot settle.
#
# The captures all start mid-conversation. Each capture came from Frida
# attached to an app that was already connected to a live DEQ. So they show
# the steady state and not the cold start.
#
# The emulator shows the cold start. Driving the real app against a fake
# accessory on 2026-10-07 reproduced the APK's own STARTUP_STEPS on live
# traffic, and it opens with COMMAND_SYNC (0x00):
#
#   0x00 0x21 0x17 0x15 0x16 0x03 0x04 0x0a 0x20 0x1f 0x09 0x05 0x06
#   0x19 0x0d 0x0b 0x1a   then 0x02 as a keepalive
#
# So "the app never sends 0x00" is true of the captures and false of the
# app. The app sends it once, first, before any capture attaches.
#
# The DEQ does wait for it. It answered 0x00 in 40ms on 2026-10-07, and
# nothing else has ever drawn a reply.
COMMAND_SYNC = 0x00
OPENING_COMMAND = COMMAND_SYNC

# The body COMMAND_SYNC must carry.
#
# The DEQ refuses a 0x00 with an empty body. It answers STATUS -5 and then
# ignores every frame after it. The 2026-10-08 car session measured that,
# and it is why the seven reads drew nothing.
#
# These are the app's own 24 bytes, and every part is a constant.
# b/e/b.h() writes a 16-byte literal from b/a/e$a.b, then a boolean that
# is false, then a zero int. Two checks agree: the APK literal decodes to
# these bytes, and five emulator cold starts put these bytes on the wire.
#
# A real unit accepted these bytes on 2026-10-08: it answered this frame
# and the nine after it, every one with STATUS 0.
SYNC_BODY = bytes.fromhex("a5c543847b356c8c408b701679ce1f110000000000000000")

# The transaction id the first frame carries.
#
# The emulator showed it on 2026-10-07. The real app's cold start opens at
# transaction id **1** and counts up: 1 for 0x00, 2 for 0x21, 3 for 0x17,
# and so on. The captured sessions open at 0x3a and 0x4e, because each
# capture joined a session that was already running.
#
# The id must change per frame. A fixed one made every frame after the
# first a repeat of one the unit had already answered.
#
# A cold start is 0x00 at id 1. A mid-session resume is 0x02 at a high id.
# OPENING_COMMAND picks the id to match.
FIRST_TRANSACTION_ID = 1 if OPENING_COMMAND == COMMAND_SYNC else 0x3A
TRANSACTION_ID_WRAP = 0x100

# COMMAND_KEEPALIVE (0x02) with no body. The app sends it every nine
# seconds for the whole session.
#
# The tablet captures contain only commands 0x02, 0x05, 0x0d and 0x0f,
# and 0x02 is most of it: 212 writes out of 359. They hold no 0x00,
# because each one started mid-session. The cold start opens with 0x00.
#
# Those captures also settle a larger question: a frame taken from
# /dev/usb_accessory decodes cleanly with the codec built from the OTG
# path in the APK, direction byte and all. Both paths share the framing,
# so there is no separate AOA protocol to reverse.
COMMAND_KEEPALIVE = 0x02

# Mid-session traffic from the real app, with the gap that comes
# **before** each frame, both read from its own captured traffic.
# SEND_BURST is False, so this program does not send it. The table stays
# as a record, and `backend/app/test_pi_gadget_encoder.py` encodes it.
#
# The 0x0d bodies are little-endian int32 and descend: -14, -15, -16 and
# so on. 0x0d is volume, so the app pushes the volume it holds. The 0x0f
# frames are mute writes.
#
# The Frida hook logs each write three times, once per file descriptor.
# So one real write looks like three in the capture. There is **one**
# opening keepalive.
STARTUP_BURST = (
    (9.03, 0x02, b""),
    (1.64, 0x0D, bytes.fromhex("f2ffffff")),
    (0.30, 0x0D, bytes.fromhex("f1ffffff")),
    (0.34, 0x0D, bytes.fromhex("f0ffffff")),
    (0.14, 0x0D, bytes.fromhex("efffffff")),
    (0.26, 0x0D, bytes.fromhex("eeffffff")),
    (0.20, 0x0D, bytes.fromhex("edffffff")),
    (0.25, 0x0D, bytes.fromhex("ecffffff")),
    (0.14, 0x0D, bytes.fromhex("ebffffff")),
    (0.63, 0x0F, bytes.fromhex("01000000")),
    (1.35, 0x0F, bytes.fromhex("00000000")),
)

# The opening part of the app's cold start, sent after COMMAND_SYNC.
#
# The app's full sequence, measured in the emulator, is:
#
#   0x00 0x21 0x17 0x15 0x16 0x03 0x04 0x0a 0x20 0x1f 0x09
#   0x05 0x06 0x19 0x0d 0x0b 0x1a   then 0x02 as a keepalive
#
# This program sends nine of those. Seven only read and carry an **empty
# body** in the app's own traffic, so this program invents nothing here:
#
#   0x17 GET_SYSTEM_ERROR_FLAGS   0x15 GET_CRASH_REPORT
#   0x03 GET_VERSION              0x04 GET_HW_INFORMATION
#   0x0a GET_USER_LOG             0x20 GET_USB_CONDITIONER_CONFIGURATION_TABLE
#   0x09 READ_USER_CONFIGURATION
#
# The other two carry a body the app also sends. 0x06
# GET_OPAL_CONFIGURATION only reads. 0x21 SET_TIMEOUT_INTERVAL does not:
# it sets one timeout, and the app sends it before any read.
#
# Seven are deliberately left out. This program changes nothing on the
# unit. The backend owns every write, and it sends 0x0b and 0x1a at the
# end of its own connect:
#
#   0x16 ERASE_CRASH_REPORT   clears the unit's own crash log
#   0x1f SET_USB_CONDITIONER_CONFIGURATION_TABLE   a SET, three fields
#   0x05 the tuning coefficients, 4209 bytes
#   0x19 SELF_SAVE_OPAL_CONFIGURATION_ENABLE
#   0x0d SET_VOLUME   0x0b SET_MODE
#   0x1a PLAY_READY_NOTIFICATION, with no body
#
# The gaps are the app's own, measured in the emulator on 2026-10-07: the
# app sends these back to back, about 100ms apart, with no long pause
# until the keepalives start.
#
# 0x21's body is the app's own, from b/e/ai.h(): the transaction id and
# then one 4-byte TIMEOUT_INTERVAL. b/e/ai.k() hardcodes it to 0x2710,
# which is 10000, so there is nothing to choose.
SET_TIMEOUT_INTERVAL_BODY = bytes.fromhex("10270000")

# 0x06's body is b/e/i.h(): the transaction id and then one 4-byte
# CONFIG_ID. b/e.d() sets it to 0 with `const/4 v5, 0x0`, so the app
# always asks for configuration 0 at cold start.
GET_OPAL_CONFIGURATION_BODY = bytes.fromhex("00000000")

COLD_START_READS = (
    (0.33, 0x21, SET_TIMEOUT_INTERVAL_BODY),
    (0.10, 0x17, b""),
    (0.10, 0x15, b""),
    (0.10, 0x03, b""),
    (0.10, 0x04, b""),
    (0.10, 0x0A, b""),
    (0.10, 0x20, b""),
    (0.10, 0x09, b""),
    (0.10, 0x06, GET_OPAL_CONFIGURATION_BODY),
)

# Send the read-only cold start after COMMAND_SYNC. Needs OPENING_COMMAND
# to be COMMAND_SYNC: these frames follow a CONNECT and mean nothing
# without one.
SEND_COLD_START_READS = True

# Send the burst once the link is up. Set False to send keepalives only.
#
# **Off, and leave it off.** It writes to the car.
#
# The burst is mid-session traffic copied from a capture of the real app,
# and it was worth sending while the question was whether frame content
# could draw a reply. That question has its answer now: the unit was
# refusing a bodyless COMMAND_SYNC, and with the body in place it answers
# everything.
#
# The table holds eight 0x0d VOLUME writes and two
# 0x0f mute writes, carrying the captured tablet's own values. So every
# connect pushed somebody else's volume into this car: on 2026-10-08 it
# ramped the unit down to -21 and sent two mute writes. A read-only
# connect must not do that, and the backend owns the conversation now
# anyway.
#
# The table stays in this file. It records what the app sends mid-session,
# which is worth keeping, even though nobody should replay it at a unit.
SEND_BURST = False

# Let the backend drive the link instead of this program.
#
# Two writers on one accessory handle interleave frames, so only one of
# them may talk to the DEQ. This program owns the handle. It answers the
# mode-switch request, re-enumerates the gadget and feeds the audio
# function. So it keeps the handle and relays whole frames over a Unix
# socket instead of giving the fd away.
#
# While a backend is on the socket, this program sends nothing of its own: no
# cold start, no burst, no keepalive. The session the backend runs carries
# all three, and two keepalive clocks on one link is the same interleaving
# problem in a slower form. The moment the backend detaches, this program
# takes the conversation back over with a keepalive, so a backend that
# stops does not drop the link.
#
# The backend reaches this through `DEQ_TRANSPORT=accessory`. See
# `backend/app/accessory_transport.py`.
RELAY_TO_BACKEND = True

# Where to listen. A path, not a port, so only a process on this Pi can
# reach it and no firewall rule has to protect it. Must match
# ACCESSORY_SOCKET_PATH in the backend's accessory transport.
RELAY_SOCKET_PATH = "/run/deq-accessory.sock"

# How long a relayed read waits before it checks whether the link is still
# up. The socket has no frame clock of its own, so this is only how often
# the relay thread wakes to look at `link_is_up`.
RELAY_POLL_SECONDS = 0.5

# How long to wait for a backend to attach before opening the session here
# instead.
#
# It has to cover a whole retry cycle of the backend's LinkKeeper, not the
# time one process takes to notice a socket. The keeper only tries to
# connect when it next wakes, so the wait depends on where in its cycle
# the socket appeared. The wait is anything from zero to a full period.
#
# 2.0 was too short and cost a failed connect in a car on 2026-10-08:
#
#   +4250.8  the relay starts listening
#   +4252.8  this program gives up waiting and sends its own 0x00
#   +4253.3  the backend attaches, 0.46s too late
#   +4253.4  its connect fails: "sent command 0x21, got a reply to 0x15",
#            because two openers put the conversation one reply out of step
#   +4256.4  its retry succeeds
#
# So this must exceed DEFAULT_RETRY_SECONDS in deq_device.py, which is
# 3.0. It must also stay inside ONLINE_WAIT_SECONDS, because the DEQ gives
# up on a device that never writes. There is room, because that is 6.0.
BACKEND_ATTACH_WAIT_SECONDS = 4.5

# Write audio into the gadget's audio function for the whole session.
#
# **Off by default: use it only for a test, or to play our own
# audio on purpose.** It does not silence the car. A tone fed on
# 2026-10-08 was inaudible under THROUGH and audible under mode 5, and
# the car's own audio played under THROUGH with this feed running.
#
# The DEQ does not wait for a stream before it talks. It answered every
# frame of the cold start on 2026-10-08 with the body on COMMAND_SYNC, and
# the feed changed nothing about the conversation. See WITH_AUDIO for why
# the function itself must stay.
FEED_AUDIO = False

# What to write. 0 feeds silence, which cannot damage an amplifier or a
# speaker. Any other value feeds a tone. On mode 5 the tone reaches the
# car's speakers at whatever volume the DEQ holds, so set one only
# deliberately, and only for a test.
AUDIO_FEED_TONE_HZ = 0

# The gadget's audio card carries this name. ALSA builds the name from the
# function, so it does not change with the card number, which does.
AUDIO_CARD_NAME = "UAC1Gadget"

# How long to wait for the audio card to appear after the gadget binds.
# ALSA registers it when the host selects the streaming interface, so it
# does not exist the moment bind returns.
AUDIO_CARD_WAIT_SECONDS = 10.0
DIRECTION_TO_DEVICE = 1
FRAME_START_MARKER = 0xF0
FRAME_END_MARKER = 0xF7
FRAME_HEADER = bytes([0x00, 0x40, 0x06, 0x00, 0x00, 0x00, 0x01])
PAYLOAD_HEADER_LENGTH = 16
LENGTH_FIELD_BIAS = 8


def build_frame(command_id, transaction_id, body=b""):
    """Returns one frame for this command, id and body.

    This repeats backend/app/deq_protocol.py's encoder rather than
    importing it, because this program runs on the Pi with no copy of
    the backend beside it. Keep the two in step.
    """
    payload = bytearray(PAYLOAD_HEADER_LENGTH)
    payload[0:2] = DIRECTION_TO_DEVICE.to_bytes(2, "little")
    payload[2:4] = command_id.to_bytes(2, "little")
    payload[4:8] = (
        PAYLOAD_HEADER_LENGTH + len(body) - LENGTH_FIELD_BIAS
    ).to_bytes(4, "little")
    payload[8:16] = transaction_id.to_bytes(8, "little")
    payload += body
    frame = bytearray([FRAME_START_MARKER])
    frame += FRAME_HEADER
    for payload_byte in payload:
        frame.append((payload_byte >> 4) & 0x0F)
        frame.append(payload_byte & 0x0F)
    frame.append(FRAME_END_MARKER)
    return bytes(frame)


def build_keepalive_frame(transaction_id):
    """Returns one COMMAND_KEEPALIVE frame with this transaction id."""
    return build_frame(COMMAND_KEEPALIVE, transaction_id)


def read_seconds_since_boot():
    """Returns the seconds since boot, the clock dmesg counts in.

    The driver's trace is the only place the interface number and the
    completion errors show up, and dmesg stamps every line with this
    clock. Reading the same clock here lets one log line pair with one
    driver line.
    """
    with open("/proc/uptime") as handle:
        return float(handle.read().split()[0])


def log(message):
    """Prints with a wall-clock time and the seconds since boot.

    An untimestamped log cost a whole car trip. Two sessions looked
    identical, and nothing showed which host connected or whether the
    board ran at all.

    The wall-clock time alone is not enough. The Pi has no RTC, so it
    boots with the time of the last save and NTP sets it right later. In
    the car the correction can arrive minutes in, or never, so the
    wall-clock time of an early line can be hours wrong. The seconds
    since boot always rise by one per second and match dmesg, so they
    order the session even when the date is wrong.
    """
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(
        f"[{stamp}] [+{read_seconds_since_boot():9.3f}s] {message}",
        flush=True,
    )


def write_file(path, value):
    with open(path, "w") as handle:
        handle.write(value)


def run_command(arguments):
    subprocess.run(arguments, check=False)


def find_udc():
    controllers = os.listdir("/sys/class/udc")
    if not controllers:
        raise RuntimeError(
            "No USB device controller found. Check that dtoverlay=dwc2 is set "
            "and that the Pi is connected through its data port.")
    return controllers[0]


def bind_gadget():
    write_file(f"{GADGET_ROOT}/UDC", find_udc())
    log(f"Bound to {find_udc()}")


def unbind_gadget():
    write_file(f"{GADGET_ROOT}/UDC", "\n")


def remove_existing_gadget():
    """Takes down a gadget left behind by an earlier run."""
    if not os.path.isdir(GADGET_ROOT):
        return
    try:
        unbind_gadget()
    except OSError:
        pass
    time.sleep(0.2)
    # ffs.deq is here for the FunctionFS gadget this program replaced. A
    # leftover link to it stops the new gadget from starting at all: the
    # function has no descriptors, so the UDC refuses with ENODEV, which
    # surfaces as EBUSY on the bind and says nothing about the cause.
    for function_name in ("accessory.deq", AUDIO_FUNCTION_NAME, "ffs.deq"):
        link = os.path.join(GADGET_ROOT, "configs/c.1", function_name)
        if os.path.islink(link):
            os.unlink(link)
    for directory in ("configs/c.1/strings/0x409", "configs/c.1",
                      "functions/accessory.deq",
                      "functions/" + AUDIO_FUNCTION_NAME,
                      "functions/ffs.deq", "strings/0x409"):
        full = os.path.join(GADGET_ROOT, directory)
        if os.path.isdir(full):
            try:
                os.rmdir(full)
            except OSError:
                pass
    try:
        os.rmdir(GADGET_ROOT)
    except OSError:
        pass


def create_gadget():
    """Builds the gadget tree with the identity the DEQ expects."""
    os.makedirs(GADGET_ROOT, exist_ok=True)
    write_file(f"{GADGET_ROOT}/idVendor", f"0x{PRE_ACCESSORY_VENDOR_ID:04X}")
    write_file(f"{GADGET_ROOT}/idProduct", f"0x{PRE_ACCESSORY_PRODUCT_ID:04X}")
    write_file(f"{GADGET_ROOT}/bcdDevice", "0x0400")
    write_file(f"{GADGET_ROOT}/bcdUSB", "0x0200")
    write_file(f"{GADGET_ROOT}/bDeviceClass", "0x00")
    write_file(f"{GADGET_ROOT}/bDeviceSubClass", "0x00")
    write_file(f"{GADGET_ROOT}/bDeviceProtocol", f"0x{DEVICE_PROTOCOL:02X}")

    os.makedirs(f"{GADGET_ROOT}/strings/0x409", exist_ok=True)
    write_file(f"{GADGET_ROOT}/strings/0x409/manufacturer", MANUFACTURER)
    write_file(f"{GADGET_ROOT}/strings/0x409/product", PRODUCT)
    write_file(f"{GADGET_ROOT}/strings/0x409/serialnumber", SERIAL_NUMBER)

    os.makedirs(f"{GADGET_ROOT}/configs/c.1/strings/0x409", exist_ok=True)
    write_file(f"{GADGET_ROOT}/configs/c.1/strings/0x409/configuration", "AOA")
    # 500mA, self powered. The tablet reports both values the same way.
    write_file(f"{GADGET_ROOT}/configs/c.1/MaxPower", "500")
    write_file(f"{GADGET_ROOT}/configs/c.1/bmAttributes", "0xC0")

    link_function("accessory.deq")


def link_function(function_name):
    """Puts one function into the configuration.

    configfs can only make a function when the kernel has its module
    loaded. Two unchecked steps, a mkdir and then a symlink, hide that.
    A symlink to a directory that nobody created leaves a dangling link.
    The gadget still binds and the host still configures it while every
    endpoint is broken. So fail loudly here instead.
    """
    function_path = os.path.join(GADGET_ROOT, "functions", function_name)
    link_path = os.path.join(GADGET_ROOT, "configs", "c.1", function_name)
    if os.path.islink(link_path):
        return
    try:
        os.mkdir(function_path)
    except FileExistsError:
        pass
    except OSError as caught_error:
        raise RuntimeError(
            f"configfs refused the {function_name} function: {caught_error}. "
            f"Check that its module is loaded.") from caught_error
    os.symlink(function_path, link_path)


def enter_accessory_mode():
    """Re-enumerates with the accessory product id, and the audio sink.

    The DEQ asks for audio during the handshake, and it is a car audio
    processor. Attach the audio function here and not when the gadget is
    first built: a real Android device has no audio interface before the
    handshake, and a DEQ that sees one on the pre-accessory 18d1:4ee7
    device does not start the handshake at all.

    WITH_AUDIO drops the audio function, to test whether it is what stops
    the DEQ from reading the bulk endpoints.

    This runs with the UDC unbound, which is the only time configfs
    allows the configuration to change.
    """
    unbind_gadget()
    time.sleep(0.5)
    if WITH_AUDIO:
        product_id = ACCESSORY_PRODUCT_ID
        description = "accessory + audio"
    else:
        product_id = ACCESSORY_ONLY_PRODUCT_ID
        description = "accessory only"
    write_file(f"{GADGET_ROOT}/idProduct", f"0x{product_id:04X}")
    if WITH_AUDIO:
        run_command(["modprobe", AUDIO_MODULE_NAME])
        create_audio_function()
        if AUDIO_FIRST:
            relink_with_audio_first()
        else:
            link_function(AUDIO_FUNCTION_NAME)
    time.sleep(0.2)
    bind_gadget()
    log(f"Re-enumerated as the AOA accessory "
        f"(18d1:{product_id:04x}, {description})")
    if WITH_AUDIO:
        log(f"  audio: source, {AUDIO_SAMPLE_RATE} Hz, "
            f"{int(AUDIO_SAMPLE_SIZE) * 8}-bit, device to host")
        log(f"  audio feed: {'on' if FEED_AUDIO else 'off'}")


def create_audio_function():
    """Makes the audio function a source, the way Android's is.

    The function's attributes can only be written before it joins a
    configuration, so this runs before link_function. Making the directory
    here rather than leaving it to link_function is what gives that window.
    """
    function_path = os.path.join(GADGET_ROOT, "functions",
                                 AUDIO_FUNCTION_NAME)
    try:
        os.mkdir(function_path)
    except FileExistsError:
        pass
    settings = (
        ("p_chmask", AUDIO_PLAYBACK_CHANNEL_MASK),
        ("p_srate", AUDIO_SAMPLE_RATE),
        ("p_ssize", AUDIO_SAMPLE_SIZE),
        ("c_chmask", AUDIO_CAPTURE_DISABLED),
        ("p_mute_present", AUDIO_CONTROL_ABSENT),
        ("p_volume_present", AUDIO_CONTROL_ABSENT),
        ("c_mute_present", AUDIO_CONTROL_ABSENT),
        ("c_volume_present", AUDIO_CONTROL_ABSENT),
        ("req_number", AUDIO_REQUEST_COUNT),
    )
    if AUDIO_FUNCTION_TYPE == "uac1deq":
        settings += (
            ("p_fu_empty", AUDIO_FEATURE_UNIT_EMPTY),
            ("ac_in_collection", AUDIO_CONTROL_IN_COLLECTION),
        )
    for name, value in settings:
        try:
            write_file(os.path.join(function_path, name), value)
        except OSError as caught_error:
            log(f"could not set audio {name}: {caught_error}")


def relink_with_audio_first():
    """Puts the audio function ahead of the accessory one.

    configfs numbers interfaces in link order, so unlinking the accessory
    function and linking it again after the audio one moves it off
    interface 0. The UDC must already be unbound, which is true for every
    caller of this function.
    """
    accessory_link = os.path.join(GADGET_ROOT, "configs", "c.1",
                                  "accessory.deq")
    if os.path.islink(accessory_link):
        os.unlink(accessory_link)
    link_function(AUDIO_FUNCTION_NAME)
    link_function("accessory.deq")
    log("  linked audio first, so the accessory interface is not 0")


def reset_to_pre_accessory_mode():
    """Puts the gadget back to the identity the DEQ probes first.

    A DEQ that gave up on accessory mode starts the whole handshake
    again, and it expects to find the pre-accessory device when it does,
    not the accessory one it just abandoned.
    """
    unbind_gadget()
    time.sleep(0.5)
    write_file(f"{GADGET_ROOT}/idProduct", f"0x{PRE_ACCESSORY_PRODUCT_ID:04X}")
    audio_link = os.path.join(GADGET_ROOT, "configs", "c.1",
                             AUDIO_FUNCTION_NAME)
    if os.path.islink(audio_link):
        os.unlink(audio_link)
    # Remove the function itself, not only the link. Its attributes can
    # only be written while it belongs to no configuration, so the next
    # cycle has to build it again to set them.
    audio_function = os.path.join(GADGET_ROOT, "functions",
                                 AUDIO_FUNCTION_NAME)
    if os.path.isdir(audio_function):
        try:
            os.rmdir(audio_function)
        except OSError as caught_error:
            log(f"could not remove the audio function: {caught_error}")
    # AUDIO_FIRST relinks the accessory function, so make sure it is
    # linked and is the only function here. The DEQ probes this device, and
    # it must look the same on every cycle.
    link_function("accessory.deq")
    time.sleep(0.2)
    bind_gadget()
    log("Back to the pre-accessory device, waiting for the next handshake.")


def wait_for_start_request(accessory_descriptor):
    """Blocks until the DEQ asks this device to enter accessory mode.

    The driver answers GET_PROTOCOL, collects the host's identification
    strings and records the START request. This only has to notice that
    it happened. Android watches a uevent for it. Polling the ioctl is
    the same answer with far less machinery.
    """
    while True:
        if fcntl.ioctl(accessory_descriptor, ACCESSORY_IS_START_REQUESTED):
            audio_mode = fcntl.ioctl(accessory_descriptor,
                                     ACCESSORY_GET_AUDIO_MODE)
            log(f"The DEQ asked for accessory mode, audio mode {audio_mode}.")
            log("The strings the DEQ sent:")
            log_host_strings(accessory_descriptor)
            return
        time.sleep(START_POLL_SECONDS)


def log_host_strings(accessory_descriptor):
    """Logs the six strings the DEQ sent during the handshake.

    These are the host's own identification, not this device's. They are
    the only thing the DEQ says about itself before any frame, so they are
    the place to look when it starts the handshake and then gives up.
    """
    for name, request in ACCESSORY_STRING_IOCTLS:
        buffer = bytearray(ACCESSORY_STRING_LENGTH)
        try:
            fcntl.ioctl(accessory_descriptor, request, buffer)
        except OSError as caught_error:
            log(f"  {name}: could not read it ({caught_error})")
            continue
        value = buffer.split(b"\x00", 1)[0].decode("utf-8", "replace")
        log(f"  {name}: {value}")


def opening_command_body():
    """Returns the body OPENING_COMMAND needs.

    Only COMMAND_SYNC carries one. COMMAND_KEEPALIVE takes an empty body,
    so flipping OPENING_COMMAND back still sends a valid frame.
    """
    if OPENING_COMMAND == COMMAND_SYNC:
        return SYNC_BODY
    return b""


def wait_until_writable(accessory_descriptor, transaction_id):
    """Sends OPENING_COMMAND as soon as the DEQ configures the device.

    The Sound & Tune app speaks first. On the tablet, Android starts the
    app once the accessory connects, and the app writes before the DEQ
    sends anything. The DEQ's own identification
    string says so too: "Supported application is not installed." A
    device that only listens gives it nothing to answer.

    A write can only succeed after the DEQ configures the device.
    acc_write returns ENODEV until then, and unlike acc_read it does
    not wait. This runs right after the request for re-enumeration, so
    retry until the link is up or the DEQ gives up.

    Returns True when the frame went out.
    """
    deadline = time.monotonic() + ONLINE_WAIT_SECONDS
    while time.monotonic() < deadline:
        if send_command(accessory_descriptor, OPENING_COMMAND,
                        transaction_id, opening_command_body()):
            return True
        time.sleep(ONLINE_POLL_SECONDS)
    log("the DEQ never configured this device, so nothing was sent")
    return False


def send_keepalive(accessory_descriptor, transaction_id):
    """Writes one keepalive. Returns True when the DEQ took it."""
    return send_command(accessory_descriptor, COMMAND_KEEPALIVE,
                        transaction_id)


def send_command(accessory_descriptor, command_id, transaction_id, body=b""):
    """Writes one frame. Returns True when the DEQ took it."""
    frame = build_frame(command_id, transaction_id, body)
    try:
        written = os.write(accessory_descriptor, frame)
    except OSError as caught_error:
        if caught_error.errno != errno.ENODEV:
            log(f"could not send command {command_id:#04x}: {caught_error}")
        return False
    log(f"sent command {command_id:#04x}, transaction id "
        f"{transaction_id:#04x}, {written} bytes")
    return True


def send_cold_start_reads(accessory_descriptor, transaction_id):
    """Sends the opening part of the app's cold start.

    Runs straight after COMMAND_SYNC, which the DEQ answers. Every frame
    but the first only reads, so a reply is new information and nothing
    changes on the unit. The first is 0x21 SET_TIMEOUT_INTERVAL, which
    sets one timeout on the unit and which the app sends before any read.
    See COLD_START_READS for what this leaves out and why.

    Returns the next transaction id and whether every frame went out.
    """
    log("sending the opening part of the app's cold start")
    for gap_seconds, command_id, body in COLD_START_READS:
        if gap_seconds > 0:
            time.sleep(gap_seconds)
        if not send_command(accessory_descriptor, command_id,
                            transaction_id, body):
            return transaction_id, False
        transaction_id = next_transaction_id(transaction_id)
    return transaction_id, True


def send_startup_burst(accessory_descriptor, transaction_id):
    """Sends the app's captured mid-session traffic, and returns the next id.

    This burst comes from a capture, and every capture starts
    mid-conversation. Each capture came from a hook on an app that was
    already connected. So these are frames the app sends once a session
    is running, not frames that open one.

    The DEQ answers them in the capture and ignores them here, which is
    what that difference predicts. COMMAND_SYNC and COLD_START_READS are
    what open a session.
    """
    log("sending the app's startup burst, with the app's own gaps")
    for gap_seconds, command_id, body in STARTUP_BURST:
        # The gap comes before the frame. The nine seconds before the
        # second keepalive is the whole reason this table carries times.
        if gap_seconds > 0:
            time.sleep(gap_seconds)
        if not send_command(accessory_descriptor, command_id, transaction_id,
                            body):
            return transaction_id, False
        transaction_id = next_transaction_id(transaction_id)
    return transaction_id, True


def log_incoming_frames(accessory_descriptor, link_is_up, relay=None):
    """Logs every frame the DEQ sends, until the link stops.

    This runs in its own thread because acc_read blocks with no timeout,
    and the keepalive clock must keep running while it waits. Clearing
    `link_is_up` is how it tells the keepalive loop to stop.

    A frame starts 0xf0 and ends 0xf7. See
    backend/app/deq_protocol.py for what the bytes mean.

    This logs every frame, with or without a backend on the socket. The
    log is the only record of a car session, and a relayed session needs
    that record most.
    """
    while True:
        try:
            frame = os.read(accessory_descriptor, 16384)
        except OSError as caught_error:
            log(f"the accessory link stopped: {caught_error}")
            break
        if not frame:
            log("the accessory link closed")
            break
        log(f"received {len(frame)} bytes: {frame.hex()}")
        if relay is not None:
            relay.send_to_backend(frame)
    link_is_up.clear()
    if relay is not None:
        relay.stop()


class BackendRelay:
    """Lets the backend drive the DEQ through this program's handle.

    It carries whole frames both ways over a Unix socket. You call
    `start`, then `is_attached` to see whether the backend has the
    conversation, and `send_to_backend` for each frame the DEQ sends. It
    depends on the accessory handle this program already holds.

    One backend at a time. This class refuses a second connection and
    does not queue it. Two writers is the problem this class exists to
    prevent, and a second connection would bring it back one layer up.
    """

    def __init__(self, accessory_descriptor, socket_path=RELAY_SOCKET_PATH):
        self.accessory_descriptor = accessory_descriptor
        self.socket_path = socket_path
        self.listener = None
        self.connection = None
        self.running = threading.Event()
        self._send_lock = threading.Lock()

    def start(self):
        """Starts listening. Returns True when the socket is up."""
        # A socket file outlives the process that made it, so a crash
        # leaves one behind and `bind` then fails with EADDRINUSE.
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass
        except OSError as caught_error:
            log(f"could not clear {self.socket_path}: {caught_error}")
            return False
        try:
            self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.listener.bind(self.socket_path)
            self.listener.listen(1)
            self.listener.settimeout(RELAY_POLL_SECONDS)
        except OSError as caught_error:
            log(f"could not listen on {self.socket_path}: {caught_error}")
            return False
        # The backend does not run as root, and the socket takes root's
        # own mode by default.
        try:
            os.chmod(self.socket_path, 0o666)
        except OSError as caught_error:
            log(f"could not open up {self.socket_path}: {caught_error}")
        self.running.set()
        threading.Thread(target=self._serve, daemon=True).start()
        log(f"relaying to a backend on {self.socket_path}")
        return True

    def is_attached(self):
        """True while a backend holds the conversation."""
        return self.connection is not None

    def wait_for_backend(self, timeout_seconds=BACKEND_ATTACH_WAIT_SECONDS):
        """Waits a short while for a backend to attach. Returns whether one did.

        The wait covers one retry cycle of the backend's own link keeper,
        which is what decides when it reaches for the socket. When no
        backend is running at all, this program opens the session itself
        rather than leaving the DEQ unanswered.

        Returning False and then having a backend attach anyway is the
        case that costs a failed connect: both ends open the session and
        the conversation goes one reply out of step. `run_accessory_session`
        checks once more after this returns, so a backend that arrives
        during the opening write still takes over cleanly.
        """
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self.is_attached():
                return True
            time.sleep(RELAY_POLL_SECONDS)
        return self.is_attached()

    def _serve(self):
        """Accepts backends, and relays for the one that holds the link.

        Accepting never stops while the relay runs. A second backend has
        to be told so, and a connection left in the listen backlog tells
        it nothing: it would sit there looking connected and time out on
        every read. So this thread only accepts, and a separate thread
        relays for each backend.
        """
        while self.running.is_set():
            try:
                connection, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError as caught_error:
                if self.running.is_set():
                    log(f"the relay stopped accepting: {caught_error}")
                return
            if self.connection is not None:
                log("a second backend tried to attach; refusing it")
                try:
                    connection.close()
                except OSError:
                    pass
                continue
            log("a backend attached and now drives the link")
            self.connection = connection
            threading.Thread(
                target=self._relay_until_detached,
                args=(connection,),
                daemon=True).start()

    def _relay_until_detached(self, connection):
        """Relays one backend's frames, and gives the link back when it goes."""
        try:
            self._relay_from_backend(connection)
        finally:
            self.connection = None
            try:
                connection.close()
            except OSError:
                pass
            log("the backend detached; this program drives the link again")

    def _relay_from_backend(self, connection):
        """Writes everything the backend sends to the DEQ, until it stops."""
        connection.settimeout(RELAY_POLL_SECONDS)
        while self.running.is_set():
            try:
                data = connection.recv(16384)
            except socket.timeout:
                continue
            except OSError as caught_error:
                log(f"reading from the backend failed: {caught_error}")
                return
            if not data:
                return
            try:
                os.write(self.accessory_descriptor, data)
            except OSError as caught_error:
                log(f"the DEQ refused {len(data)} bytes from the backend: "
                    f"{caught_error}")
                return

    def send_to_backend(self, frame):
        """Passes one frame the DEQ sent on to the attached backend."""
        connection = self.connection
        if connection is None:
            return
        with self._send_lock:
            try:
                connection.sendall(frame)
            except OSError as caught_error:
                log(f"could not pass a frame to the backend: {caught_error}")

    def stop(self):
        """Stops listening and drops any attached backend. Safe to repeat."""
        if not self.running.is_set():
            return
        self.running.clear()
        # Closing the backend's socket is what tells it the session ended,
        # which it reports as a dead link rather than a slow reply.
        for closable in (self.connection, self.listener):
            if closable is None:
                continue
            try:
                closable.close()
            except OSError:
                pass
        self.connection = None
        self.listener = None
        try:
            os.unlink(self.socket_path)
        except OSError:
            pass


def next_transaction_id(transaction_id):
    """Returns the id the next frame carries.

    The id is one byte wide on the wire, so a long session wraps. It wraps
    back to the first id rather than to zero: zero is a value the DEQ sees
    before any frame of this session, so reusing it would look like a
    repeat.
    """
    following = transaction_id + 1
    if following >= TRANSACTION_ID_WRAP:
        return FIRST_TRANSACTION_ID
    return following


def find_audio_card_number():
    """Returns the gadget audio card's number, or None if it is absent.

    The number is not fixed. The HDMI card takes 0 on this Pi, so the
    gadget card is usually 1, but a card that appears earlier moves it.
    Read the name instead.
    """
    try:
        with open("/proc/asound/cards") as handle:
            card_lines = handle.read().splitlines()
    except FileNotFoundError:
        return None
    for line in card_lines:
        if AUDIO_CARD_NAME not in line:
            continue
        fields = line.split()
        if fields and fields[0].isdigit():
            return int(fields[0])
    return None


def wait_for_audio_card():
    """Waits for the gadget audio card, and returns its number or None.

    ALSA registers the card when the host selects the streaming
    interface, not when the gadget binds, so the card is missing for a
    moment after re-enumeration.
    """
    deadline = time.monotonic() + AUDIO_CARD_WAIT_SECONDS
    while time.monotonic() < deadline:
        card_number = find_audio_card_number()
        if card_number is not None:
            return card_number
        time.sleep(0.25)
    return None


def build_audio_feed_command(card_number):
    """Returns the command that writes one endless stream to the card.

    The gadget is a source, so its ALSA node is a playback device and the
    program writes to it with aplay. The DEQ reads what it writes.

    `arecord` is for the other configuration and would fail here. A test
    on 2026-10-07 ran both. With the old capture-only settings, `aplay`
    reported "No such file or directory", because the card had no
    playback node. `arecord` opened the capture node and then failed
    with an I/O error, because the DEQ sends no audio. It waits to
    receive some.

    The format matches what create_audio_function sets, because the
    gadget offers one format and ALSA does not resample for it.
    """
    device = f"hw:{card_number},0"
    sample_format = "S16_LE" if AUDIO_SAMPLE_SIZE == "2" else "S32_LE"
    if AUDIO_FEED_TONE_HZ > 0:
        return [
            "speaker-test",
            "--device", device,
            "--channels", "2",
            "--rate", AUDIO_SAMPLE_RATE,
            "--format", sample_format,
            "--test", "sine",
            "--frequency", str(AUDIO_FEED_TONE_HZ),
        ]
    return [
        "aplay",
        "--device", device,
        "--channels", "2",
        "--rate", AUDIO_SAMPLE_RATE,
        "--format", sample_format,
        "/dev/zero",
    ]


def start_audio_feed():
    """Starts writing audio to the gadget's audio card.

    Returns the process, or None if the card never appeared. The caller
    must stop it: a writer that outlives the session holds the card open
    and the next session's card then fails to open.
    """
    card_number = wait_for_audio_card()
    if card_number is None:
        log(f"  audio feed: no card named {AUDIO_CARD_NAME} appeared in "
            f"{AUDIO_CARD_WAIT_SECONDS:.0f}s. Not feeding.")
        return None
    command = build_audio_feed_command(card_number)
    feed = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE)
    content = "silence" if AUDIO_FEED_TONE_HZ == 0 else \
        f"a {AUDIO_FEED_TONE_HZ} Hz tone"
    log(f"  audio feed: writing {content} to hw:{card_number},0 "
        f"with {command[0]}")
    return feed


def report_audio_feed_if_it_died(feed, already_reported):
    """Logs once if the writer stopped on its own, and says so.

    This exists because a dead feed was invisible. On 2026-10-07 the
    writer exited a moment after it started, nothing noticed, and the log
    still read "writing silence" an hour later. A session then looks like
    it tested the audio stream when it tested nothing.

    Returns True once this reports the death, so the caller does not log
    the same death on every keepalive.
    """
    if feed is None or already_reported:
        return already_reported
    exit_code = feed.poll()
    if exit_code is None:
        return False
    error_text = feed.stderr.read().decode("utf-8", "replace").strip()
    last_line = error_text.splitlines()[-1] if error_text else "No message."
    log(f"  audio feed: the writer stopped on its own, code {exit_code}. "
        f"{last_line}")
    log("  audio feed: this session is NOT feeding audio.")
    return True


def stop_audio_feed(feed):
    """Stops the audio writer and logs why it stopped, if it stopped early.

    A writer that exits on its own says something: the card went away, or
    ALSA refused the format. Both are worth seeing in the log, so read what
    it put on stderr.
    """
    if feed is None:
        return
    exit_code = feed.poll()
    if exit_code is None:
        feed.terminate()
        try:
            feed.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            feed.kill()
            feed.wait(timeout=2.0)
        log("  audio feed: stopped with the session.")
        return
    error_text = feed.stderr.read().decode("utf-8", "replace").strip()
    log(f"  audio feed: the writer exited early, code {exit_code}. "
        f"{error_text.splitlines()[-1] if error_text else 'No message.'}")


# What `vcgencmd get_throttled` reports. The low bits are now, the high
# bits are "it happened at some point since this boot".
UNDERVOLTAGE_NOW = 0x1
UNDERVOLTAGE_SINCE_BOOT = 0x10000


def log_power_state(moment):
    """Logs a brown-out, so a power fault is never read as a DEQ timeout.

    This matters for one measurement in particular. A session that ends
    needs a cause, and "the DEQ dropped the link" and "the Pi lost power"
    look identical in a log that records neither. The run on 2026-10-07
    ended at sixty-three and a half minutes with no way to tell which it
    was.

    A reboot clears the bits, so this catches a brown-out that
    the Pi survived, not one that killed it. For the one that kills it,
    read the persistent journal instead.
    """
    try:
        output = subprocess.run(
            ["vcgencmd", "get_throttled"],
            capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception as caught_error:
        log(f"  power: cannot read vcgencmd ({caught_error})")
        return
    _, _, value_text = output.partition("=")
    try:
        flags = int(value_text, 16)
    except ValueError:
        log(f"  power: cannot read {output!r}")
        return
    if flags & UNDERVOLTAGE_NOW:
        log(f"  power ({moment}): **UNDER-VOLTAGE NOW**. {output}")
    elif flags & UNDERVOLTAGE_SINCE_BOOT:
        log(f"  power ({moment}): under-voltage happened earlier this boot. "
            f"{output}")
    else:
        log(f"  power ({moment}): fine. {output}")


def log_session_end(session_started_at, reason):
    """Says how long the link lasted, and what ended it.

    How long the DEQ holds a link is a number this project needs and does
    not have. Every run so far ended when the Pi lost power with the car,
    so the logs hold a lower bound and no answer. A session that ends
    while the Pi is still running writes the real number here.

    The seconds come from the monotonic clock, not the date: the Pi has no
    RTC, and a time correction mid-session would otherwise change the
    measurement.
    """
    seconds = time.monotonic() - session_started_at
    log(f"Session ended after {seconds:.1f}s "
        f"({seconds / 60:.1f} minutes): {reason}.")
    log_power_state("at the end")


def run_accessory_session(accessory_descriptor):
    """Keeps the link alive and logs what the DEQ sends back.

    The DEQ un-configures a device that stops talking, which the driver
    reports as EIO out of the blocked read. An earlier version wrote one
    frame and then only read, and the link died about six seconds later
    every time. The real app never goes quiet: it repeats
    COMMAND_KEEPALIVE about every nine seconds for the whole session.

    The transaction id increments per frame. The DEQ mirrors it back, and
    its captured replies show it answers per id. The first keepalive of
    a session got no reply at all and the second one did. So a repeat of
    a single id is not the same as asking again.
    """
    transaction_id = FIRST_TRANSACTION_ID
    session_started_at = time.monotonic()

    # The relay comes up before the opening frame, because with a backend
    # on the socket, the backend sends that frame. The DEQ requires one
    # COMMAND_SYNC, and only one, to open a session. So whoever sends it owns
    # the conversation. A second one from here would open the session
    # twice and spend a transaction id the backend then reuses.
    relay = BackendRelay(accessory_descriptor) if RELAY_TO_BACKEND else None
    if relay is not None and not relay.start():
        log("the relay did not start; this program drives the link alone")
        relay = None

    if relay is not None and relay.wait_for_backend():
        # The backend's own session opens the link. `acc_write` returns
        # ENODEV until the DEQ configures the device, which the backend
        # sees as a failed connect and retries. `LinkKeeper` tries every
        # few seconds, so the re-enumeration window needs no handling here.
        log("a backend is attached, so it sends the opening frame")
    elif not wait_until_writable(accessory_descriptor, transaction_id):
        log_session_end(session_started_at, "the first write never succeeded")
        if relay is not None:
            relay.stop()
        return

    log_power_state("at the start")

    link_is_up = threading.Event()
    link_is_up.set()

    reader = threading.Thread(
        target=log_incoming_frames,
        args=(accessory_descriptor, link_is_up, relay),
        daemon=True)
    reader.start()

    # Start the stream before the first frame. The question is whether the
    # DEQ answers once audio runs, so it must already run when the unit is
    # first asked anything.
    audio_feed = start_audio_feed() if FEED_AUDIO else None

    backend_drives = relay is not None and relay.is_attached()
    try:
        # The reads come first: they follow COMMAND_SYNC, which the DEQ
        # has just answered, and the burst that follows is mid-session
        # traffic the unit ignores without a CONNECT in front of it.
        #
        # This skips both when a backend is on the socket. Its own session
        # sends the cold start, and these frames would interleave with it.
        if (SEND_COLD_START_READS and OPENING_COMMAND == COMMAND_SYNC
                and not backend_drives):
            transaction_id = next_transaction_id(transaction_id)
            transaction_id, sent = send_cold_start_reads(accessory_descriptor,
                                                         transaction_id)
            if not sent:
                link_is_up.clear()

        if SEND_BURST and link_is_up.is_set() and not backend_drives:
            transaction_id = next_transaction_id(transaction_id)
            transaction_id, sent = send_startup_burst(accessory_descriptor,
                                                     transaction_id)
            if not sent:
                link_is_up.clear()

        audio_feed_death_reported = False
        ending = "the DEQ dropped the link"
        while link_is_up.is_set():
            time.sleep(KEEPALIVE_SECONDS)
            if not link_is_up.is_set():
                break
            audio_feed_death_reported = report_audio_feed_if_it_died(
                audio_feed, audio_feed_death_reported)
            # The backend's own session keepalives this link, so a
            # keepalive from here would be a second writer on it. Watch
            # the clock without writing, and take over the moment the
            # backend detaches.
            if relay is not None and relay.is_attached():
                backend_drives = True
                continue
            transaction_id = next_transaction_id(transaction_id)
            if not send_keepalive(accessory_descriptor, transaction_id):
                ending = "a keepalive write failed"
                break
    finally:
        # Always stop the writer. One that outlives the session holds the
        # card open, and the next session cannot then open it.
        stop_audio_feed(audio_feed)
        # The relay's socket must go with the session. One that outlived it
        # would offer a backend a link to a DEQ that is no longer there.
        if relay is not None:
            relay.stop()

    # The reader shares one descriptor with the next session, so it must
    # be gone before this returns. It wakes on its own as soon as the DEQ
    # drops the link, because acc_read then fails instead of blocking.
    reader.join(timeout=READER_STOP_SECONDS)
    if reader.is_alive():
        log("the reader thread is still blocked in a read.")
    log_session_end(session_started_at, ending)


def main():
    if os.geteuid() != 0:
        log("Run this as root.")
        return 1

    run_command(["modprobe", "libcomposite"])
    run_command(["modprobe", "usb_f_accessory"])
    if not os.path.ismount("/sys/kernel/config"):
        run_command(["mount", "-t", "configfs", "none", "/sys/kernel/config"])

    remove_existing_gadget()
    create_gadget()

    log("Gadget built. Descriptors copy the SM-T560:")
    log(f"  {PRE_ACCESSORY_VENDOR_ID:04x}:{PRE_ACCESSORY_PRODUCT_ID:04x} "
        f"{MANUFACTURER} / {PRODUCT}")
    log(f"  USB device controller: {find_udc()}")

    # Open the accessory device before binding. The driver created it
    # with the function instance. An open handle lets the ioctls below
    # report the handshake as it happens.
    accessory_descriptor = os.open(ACCESSORY_DEVICE, os.O_RDWR)

    bind_gadget()
    log("Gadget bound. Connect the DEQ now, with its switch in AOA.")

    # The DEQ drops the link and starts again if it does not like what
    # it finds, so one pass through the handshake is not the end of the
    # program. Exiting after the first drop left nothing listening for
    # the next power cycle, and the service did not restart because
    # exiting cleanly is not a failure.
    while True:
        wait_for_start_request(accessory_descriptor)
        enter_accessory_mode()
        run_accessory_session(accessory_descriptor)
        log("Waiting for the DEQ to ask again.")
        reset_to_pre_accessory_mode()


if __name__ == "__main__":
    sys.exit(main())
