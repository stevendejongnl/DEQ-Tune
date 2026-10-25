// SPDX-License-Identifier: AGPL-3.0-or-later
//
// The ESP32-S3 as the DEQ's Android accessory, on the native USB-OTG port.
//
// The DEQ is the USB host. It looks for an Android device, asks it for
// the AOA protocol, sends six strings, asks for audio and sends START. The
// device then re-enumerates as an accessory with an audio function, and
// the frames move over the accessory's two bulk endpoints. This file does
// what pi-gadget/deq_accessory.py does on the Pi, with the three rules the
// Pi taught (see USB_CAPTURE_NOTES.md, "What the DEQ requires"):
//
//   1. AOA protocol version 2. Version 1 makes the DEQ disconnect.
//   2. Answer the AOA requests before the device is configured.
//   3. An audio function, with the accessory interface at index 2 behind
//      the AudioControl and AudioStreaming interfaces, as on the SM-T560.
//
// You call deq_usb_device_start() once. It reports each step through the
// event callback, and deq_usb_device_send() writes to the DEQ once the
// accessory is configured. It depends on esp_tinyusb.
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

// The steps of a link, in the order a working DEQ takes them.
typedef enum {
    DEQ_USB_EVENT_BUS_RESET,           // a host reset the bus
    DEQ_USB_EVENT_GET_PROTOCOL,        // the host asked for the AOA version
    DEQ_USB_EVENT_STRING,              // one of six identification strings
    DEQ_USB_EVENT_AUDIO_MODE,          // SET_AUDIO_MODE, with its value
    DEQ_USB_EVENT_START,               // START: switch to the accessory
    DEQ_USB_EVENT_ACCESSORY_PRESENTED, // re-enumerated as 18d1:2d04
    DEQ_USB_EVENT_CONFIGURED,          // the host configured the accessory
    DEQ_USB_EVENT_AUDIO_ALTERNATE,     // the host chose an audio alternate
    DEQ_USB_EVENT_UNMOUNTED,           // the host went away
    DEQ_USB_EVENT_UNHANDLED_REQUEST,   // a control request this file does not know
    DEQ_USB_EVENT_MOUNTED,             // the host configured the device, in either mode
    DEQ_USB_EVENT_SUSPENDED,           // the host stopped the bus traffic
    DEQ_USB_EVENT_RESUMED,             // the bus traffic came back
} deq_usb_event_t;

// `value` is the string index, the audio mode, the alternate setting or
// the request number. `text` is the string for DEQ_USB_EVENT_STRING.
typedef void (*deq_usb_event_cb_t)(deq_usb_event_t event, uint32_t value, const char *text);

// Called with each chunk of bytes the DEQ writes to the accessory.
typedef void (*deq_usb_bytes_cb_t)(const uint8_t *data, size_t length);

esp_err_t deq_usb_device_start(deq_usb_event_cb_t on_event, deq_usb_bytes_cb_t on_bytes);

// True once the DEQ configured the accessory and its endpoints are open.
bool deq_usb_device_is_ready(void);

// Writes one whole frame to the DEQ. Returns false when the accessory is
// not ready or the write did not fit.
bool deq_usb_device_send(const uint8_t *data, size_t length);

#ifdef __cplusplus
}
#endif
