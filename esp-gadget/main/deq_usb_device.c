// SPDX-License-Identifier: AGPL-3.0-or-later
#include "deq_usb_device.h"

#include <string.h>

#include "device/usbd_pvt.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "tinyusb.h"
#include "tusb.h"

static const char *TAG = "deq_usb";

// esp_tinyusb sets the descriptors that its own tud_descriptor_*_cb()
// hand out with this function. Its header is private to the component,
// so this file declares it. Switching to the accessory calls it a second
// time.
esp_err_t tinyusb_set_descriptors(const tinyusb_config_t *config);

// ---------------------------------------------------------------------
// AOA requests. See https://source.android.com/docs/core/interaction/accessories/aoa
// ---------------------------------------------------------------------

#define AOA_REQUEST_GET_PROTOCOL 51
#define AOA_REQUEST_SEND_STRING 52
#define AOA_REQUEST_START 53
#define AOA_REQUEST_REGISTER_HID 54
#define AOA_REQUEST_UNREGISTER_HID 55
#define AOA_REQUEST_SET_HID_REPORT_DESC 56
#define AOA_REQUEST_SEND_HID_EVENT 57
#define AOA_REQUEST_SET_AUDIO_MODE 58

// Version 2. Answer 1 and the DEQ disconnects without sending a string.
#define AOA_PROTOCOL_VERSION 2

// How long the device stays away between the two identities, so the
// host's own state machine sees it leave before it comes back.
#define REENUMERATE_DELAY_MS 250

// ---------------------------------------------------------------------
// Before START: the SM-T560's own identity, field for field (lsusb -v of
// the tablet that works with this DEQ). One ADB interface: a host drops a
// device with no interface before it sends any vendor request.
// ---------------------------------------------------------------------

#define GOOGLE_VENDOR_ID 0x18D1
#define TABLET_PRODUCT_ID 0x4EE7
// Accessory plus audio. Accessory alone (0x2D00) gets no
// SET_CONFIGURATION from the DEQ at all.
#define ACCESSORY_AUDIO_PRODUCT_ID 0x2D04

// Full speed allows 64-byte bulk packets. The tablet's are 512 at high
// speed, which the ESP32-S3 does not have. The Pi reproduced the DEQ's
// old refusal at high speed, so speed was never the cause of it.
#define BULK_PACKET_BYTES 64

static const tusb_desc_device_t s_tablet_device = {
    .bLength = sizeof(tusb_desc_device_t),
    .bDescriptorType = TUSB_DESC_DEVICE,
    .bcdUSB = 0x0200,
    .bDeviceClass = 0x00,
    .bDeviceSubClass = 0x00,
    .bDeviceProtocol = 0x01,
    .bMaxPacketSize0 = CFG_TUD_ENDPOINT0_SIZE,
    .idVendor = GOOGLE_VENDOR_ID,
    .idProduct = TABLET_PRODUCT_ID,
    .bcdDevice = 0x0400,
    .iManufacturer = 0x01,
    .iProduct = 0x02,
    .iSerialNumber = 0x03,
    .bNumConfigurations = 0x01,
};

#define TABLET_CONFIG_BYTES (TUD_CONFIG_DESC_LEN + 9 + 7 + 7)
static const uint8_t s_tablet_config[TABLET_CONFIG_BYTES] = {
    TUD_CONFIG_DESCRIPTOR(1, 1, 0, TABLET_CONFIG_BYTES, 0xC0, 500),
    // interface 0: ADB (vendor 0xFF, subclass 0x42, protocol 0x01)
    9, TUSB_DESC_INTERFACE, 0, 0, 2, 0xFF, 0x42, 0x01, 0,
    7, TUSB_DESC_ENDPOINT, 0x81, TUSB_XFER_BULK, U16_TO_U8S_LE(BULK_PACKET_BYTES), 0,
    7, TUSB_DESC_ENDPOINT, 0x01, TUSB_XFER_BULK, U16_TO_U8S_LE(BULK_PACKET_BYTES), 0,
};

// ---------------------------------------------------------------------
// After START: accessory plus audio, the tablet's shape. Android's
// f_audio_source presents AudioControl at 0 and AudioStreaming at 1, so
// the accessory lands on 2. The DEQ looks for it there: with it at 0, the
// Pi's link dropped within six seconds; at 2 it held for fifty minutes.
//
// The audio is a source, device to host: a microphone input terminal, a
// feature unit with no controls, a USB streaming output terminal, and one
// isochronous IN endpoint of 256 bytes at 44100 Hz, 16-bit stereo.
// ---------------------------------------------------------------------

static const tusb_desc_device_t s_accessory_device = {
    .bLength = sizeof(tusb_desc_device_t),
    .bDescriptorType = TUSB_DESC_DEVICE,
    .bcdUSB = 0x0200,
    .bDeviceClass = 0x00,
    .bDeviceSubClass = 0x00,
    .bDeviceProtocol = 0x00,
    .bMaxPacketSize0 = CFG_TUD_ENDPOINT0_SIZE,
    .idVendor = GOOGLE_VENDOR_ID,
    .idProduct = ACCESSORY_AUDIO_PRODUCT_ID,
    .bcdDevice = 0x0100,
    .iManufacturer = 0x01,
    .iProduct = 0x02,
    .iSerialNumber = 0x03,
    .bNumConfigurations = 0x01,
};

#define AUDIO_CONTROL_INTERFACE 0
#define AUDIO_STREAMING_INTERFACE 1
#define ACCESSORY_INTERFACE 2

#define INPUT_TERMINAL_ID 1
#define FEATURE_UNIT_ID 2
#define OUTPUT_TERMINAL_ID 3

#define AUDIO_ENDPOINT 0x82
#define AUDIO_PACKET_BYTES 256
#define AUDIO_SAMPLE_RATE 44100
#define ACCESSORY_ENDPOINT_IN 0x81
#define ACCESSORY_ENDPOINT_OUT 0x01

#define AUDIO_CONTROL_BLOCK_BYTES (10 + 12 + 9 + 9)
#define ACCESSORY_CONFIG_BYTES (TUD_CONFIG_DESC_LEN + 9 + AUDIO_CONTROL_BLOCK_BYTES + 9 + 9 + 7 + 11 + 9 + 7 + 9 + 7 + 7)

static const uint8_t s_accessory_config[ACCESSORY_CONFIG_BYTES] = {
    TUD_CONFIG_DESCRIPTOR(1, 3, 0, ACCESSORY_CONFIG_BYTES, 0xC0, 500),

    // interface 0: AudioControl
    9, TUSB_DESC_INTERFACE, AUDIO_CONTROL_INTERFACE, 0, 0, 0x01, 0x01, 0x00, 0,
    // header: UAC 1.00, both audio interfaces in the collection, as the
    // tablet lists them (upstream Linux lists only the streaming one)
    10, 0x24, 0x01, U16_TO_U8S_LE(0x0100), U16_TO_U8S_LE(AUDIO_CONTROL_BLOCK_BYTES), 2,
    AUDIO_CONTROL_INTERFACE, AUDIO_STREAMING_INTERFACE,
    // input terminal: microphone, two channels (left and right front)
    12, 0x24, 0x02, INPUT_TERMINAL_ID, U16_TO_U8S_LE(0x0201), 0, 2, U16_TO_U8S_LE(0x0003), 0, 0,
    // feature unit with no controls: bControlSize 2, one master entry of 0
    9, 0x24, 0x06, FEATURE_UNIT_ID, INPUT_TERMINAL_ID, 2, U16_TO_U8S_LE(0x0000), 0,
    // output terminal: USB streaming
    9, 0x24, 0x03, OUTPUT_TERMINAL_ID, U16_TO_U8S_LE(0x0101), 0, FEATURE_UNIT_ID, 0,

    // interface 1, alternate 0: AudioStreaming, no bandwidth
    9, TUSB_DESC_INTERFACE, AUDIO_STREAMING_INTERFACE, 0, 0, 0x01, 0x02, 0x00, 0,
    // interface 1, alternate 1: the stream
    9, TUSB_DESC_INTERFACE, AUDIO_STREAMING_INTERFACE, 1, 1, 0x01, 0x02, 0x00, 0,
    // general: linked to the output terminal, one frame delay, PCM
    7, 0x24, 0x01, OUTPUT_TERMINAL_ID, 1, U16_TO_U8S_LE(0x0001),
    // format type I: 2 channels, 2-byte subframes, 16 bits, one rate
    11, 0x24, 0x02, 0x01, 2, 2, 16, 1, (uint8_t)(AUDIO_SAMPLE_RATE & 0xFF),
    (uint8_t)((AUDIO_SAMPLE_RATE >> 8) & 0xFF), (uint8_t)((AUDIO_SAMPLE_RATE >> 16) & 0xFF),
    // isochronous IN, asynchronous; every frame at full speed
    9, TUSB_DESC_ENDPOINT, AUDIO_ENDPOINT, 0x05, U16_TO_U8S_LE(AUDIO_PACKET_BYTES), 1, 0, 0,
    // class-specific endpoint: sampling frequency control
    7, 0x25, 0x01, 0x01, 0, U16_TO_U8S_LE(0),

    // interface 2: the accessory (vendor, Google's AOA subclass 0xFF)
    9, TUSB_DESC_INTERFACE, ACCESSORY_INTERFACE, 0, 2, 0xFF, 0xFF, 0x00, 0,
    7, TUSB_DESC_ENDPOINT, ACCESSORY_ENDPOINT_IN, TUSB_XFER_BULK, U16_TO_U8S_LE(BULK_PACKET_BYTES), 0,
    7, TUSB_DESC_ENDPOINT, ACCESSORY_ENDPOINT_OUT, TUSB_XFER_BULK, U16_TO_U8S_LE(BULK_PACKET_BYTES), 0,
};

static const char *s_strings[] = {
    (const char[]){0x09, 0x04},  // English (US)
    "SAMSUNG",
    "SAMSUNG_Android",
    "0000000000000000",
};

// ---------------------------------------------------------------------
// State
// ---------------------------------------------------------------------

typedef struct {
    deq_usb_event_cb_t on_event;
    deq_usb_bytes_cb_t on_bytes;
    volatile bool start_requested;
    volatile bool accessory_presented;
    volatile bool configured;
} deq_usb_state_t;

static deq_usb_state_t s_state;

static void report(deq_usb_event_t event, uint32_t value, const char *text)
{
    if (s_state.on_event != NULL) {
        s_state.on_event(event, value, text);
    }
}

// ---------------------------------------------------------------------
// The AOA handshake. TinyUSB passes vendor requests to the device here
// before any SET_CONFIGURATION, which is rule 2.
// ---------------------------------------------------------------------

static char s_received_string[256];
static uint16_t s_received_string_index;
static uint16_t s_protocol_version = AOA_PROTOCOL_VERSION;

bool tud_vendor_control_xfer_cb(uint8_t rhport, uint8_t stage, tusb_control_request_t const *request)
{
    if (stage == CONTROL_STAGE_ACK) {
        if (request->bRequest == AOA_REQUEST_SEND_STRING) {
            size_t length = request->wLength < sizeof(s_received_string) ? request->wLength
                                                                          : sizeof(s_received_string) - 1;
            s_received_string[length] = '\0';
            report(DEQ_USB_EVENT_STRING, s_received_string_index, s_received_string);
        }
        return true;
    }
    if (stage != CONTROL_STAGE_SETUP) {
        return true;
    }
    bool to_host = (request->bmRequestType & 0x80) != 0;
    switch (request->bRequest) {
    case AOA_REQUEST_GET_PROTOCOL:
        if (!to_host) {
            break;
        }
        report(DEQ_USB_EVENT_GET_PROTOCOL, AOA_PROTOCOL_VERSION, NULL);
        return tud_control_xfer(rhport, request, &s_protocol_version, sizeof(s_protocol_version));
    case AOA_REQUEST_SEND_STRING: {
        s_received_string_index = request->wIndex;
        uint16_t length = request->wLength < sizeof(s_received_string) - 1 ? request->wLength
                                                                            : sizeof(s_received_string) - 1;
        memset(s_received_string, 0, sizeof(s_received_string));
        return tud_control_xfer(rhport, request, s_received_string, length);
    }
    case AOA_REQUEST_SET_AUDIO_MODE:
        report(DEQ_USB_EVENT_AUDIO_MODE, request->wValue, NULL);
        return tud_control_status(rhport, request);
    case AOA_REQUEST_START:
        report(DEQ_USB_EVENT_START, 0, NULL);
        s_state.start_requested = true;
        return tud_control_status(rhport, request);
    case AOA_REQUEST_REGISTER_HID:
    case AOA_REQUEST_UNREGISTER_HID:
    case AOA_REQUEST_SET_HID_REPORT_DESC:
    case AOA_REQUEST_SEND_HID_EVENT:
        // HID is part of version 2. The DEQ is not known to use it.
        report(DEQ_USB_EVENT_UNHANDLED_REQUEST, request->bRequest, NULL);
        return tud_control_status(rhport, request);
    default:
        break;
    }
    report(DEQ_USB_EVENT_UNHANDLED_REQUEST, request->bRequest, NULL);
    return false;
}

// ---------------------------------------------------------------------
// The audio function: a small class driver of its own, because TinyUSB's
// audio class speaks UAC2 and the tablet's function is UAC1. It claims
// the AudioControl and AudioStreaming interfaces, opens the isochronous
// endpoint when the host picks alternate 1, and keeps it filled with
// silence. Which audio the unit plays is the source mode's business (the
// backend's), not this function's.
// ---------------------------------------------------------------------

static uint8_t s_audio_alternate;
static const tusb_desc_endpoint_t *s_audio_endpoint_descriptor;
static uint8_t s_silence[AUDIO_PACKET_BYTES];
// 44100 Hz stereo 16-bit is 176.4 bytes per millisecond frame.
#define SILENCE_PACKET_BYTES 176
static uint8_t s_sample_rate[3] = {
    (uint8_t)(AUDIO_SAMPLE_RATE & 0xFF),
    (uint8_t)((AUDIO_SAMPLE_RATE >> 8) & 0xFF),
    (uint8_t)((AUDIO_SAMPLE_RATE >> 16) & 0xFF),
};

static void audio_init(void)
{
    memset(s_silence, 0, sizeof(s_silence));
}

static void audio_reset(uint8_t rhport)
{
    (void)rhport;
    s_audio_alternate = 0;
    s_audio_endpoint_descriptor = NULL;
}

// Claims one audio interface, with every alternate and class descriptor
// behind it. Returns the bytes taken, or 0 for an interface it does not own.
static uint16_t audio_open(uint8_t rhport, tusb_desc_interface_t const *interface, uint16_t max_length)
{
    if (interface->bInterfaceClass != 0x01) {
        return 0;
    }
    uint8_t number = interface->bInterfaceNumber;
    uint8_t const *descriptor = (uint8_t const *)interface;
    uint8_t const *end = descriptor + max_length;
    uint16_t taken = 0;
    while (descriptor < end) {
        uint8_t type = tu_desc_type(descriptor);
        if (taken > 0 && type == TUSB_DESC_INTERFACE &&
            ((tusb_desc_interface_t const *)descriptor)->bInterfaceNumber != number) {
            break;  // the next interface belongs to another driver
        }
        if (type == TUSB_DESC_ENDPOINT) {
            // An isochronous endpoint gets its FIFO room now, and goes
            // live when the host picks alternate 1.
            s_audio_endpoint_descriptor = (tusb_desc_endpoint_t const *)descriptor;
            usbd_edpt_iso_alloc(rhport, s_audio_endpoint_descriptor->bEndpointAddress, AUDIO_PACKET_BYTES);
        }
        taken += tu_desc_len(descriptor);
        descriptor = tu_desc_next(descriptor);
    }
    return taken;
}

static void audio_queue_silence(uint8_t rhport)
{
    usbd_edpt_xfer(rhport, AUDIO_ENDPOINT, s_silence, SILENCE_PACKET_BYTES, false);
}

static bool audio_control(uint8_t rhport, uint8_t stage, tusb_control_request_t const *request)
{
    tusb_request_type_t type = request->bmRequestType_bit.type;
    if (type == TUSB_REQ_TYPE_STANDARD && request->bRequest == TUSB_REQ_SET_INTERFACE) {
        if (stage != CONTROL_STAGE_SETUP) {
            return true;
        }
        if (tu_u16_low(request->wIndex) == AUDIO_STREAMING_INTERFACE) {
            s_audio_alternate = (uint8_t)request->wValue;
            report(DEQ_USB_EVENT_AUDIO_ALTERNATE, s_audio_alternate, NULL);
            if (s_audio_alternate == 1 && s_audio_endpoint_descriptor != NULL) {
                usbd_edpt_iso_activate(rhport, s_audio_endpoint_descriptor);
                audio_queue_silence(rhport);
            } else {
                usbd_edpt_close(rhport, AUDIO_ENDPOINT);
            }
        }
        return tud_control_status(rhport, request);
    }
    if (type == TUSB_REQ_TYPE_STANDARD && request->bRequest == TUSB_REQ_GET_INTERFACE) {
        if (stage != CONTROL_STAGE_SETUP) {
            return true;
        }
        return tud_control_xfer(rhport, request, &s_audio_alternate, 1);
    }
    if (type == TUSB_REQ_TYPE_CLASS) {
        // UAC1 sampling frequency, to the endpoint: take a SET_CUR, and
        // answer each GET with the one rate there is.
        if (stage != CONTROL_STAGE_SETUP) {
            return true;
        }
        return tud_control_xfer(rhport, request, s_sample_rate, sizeof(s_sample_rate));
    }
    return false;
}

static bool audio_transfer(uint8_t rhport, uint8_t endpoint, xfer_result_t result, uint32_t bytes)
{
    (void)result;
    (void)bytes;
    if (endpoint == AUDIO_ENDPOINT && s_audio_alternate == 1) {
        audio_queue_silence(rhport);
    }
    return true;
}

static const usbd_class_driver_t s_audio_driver = {
    .name = "UAC1",
    .init = audio_init,
    .reset = audio_reset,
    .open = audio_open,
    .control_xfer_cb = audio_control,
    .xfer_cb = audio_transfer,
    .sof = NULL,
};

usbd_class_driver_t const *usbd_app_driver_get_cb(uint8_t *driver_count)
{
    *driver_count = 1;
    return &s_audio_driver;
}

// ---------------------------------------------------------------------
// Mount, and the accessory's bulk data
// ---------------------------------------------------------------------

// ---------------------------------------------------------------------
// Descriptor reads. The linker wraps esp_tinyusb's callbacks (see
// CMakeLists.txt), so each read passes through here first.
// ---------------------------------------------------------------------

static volatile deq_usb_descriptor_reads_t s_descriptor_reads;

uint8_t const *__real_tud_descriptor_device_cb(void);
uint8_t const *__real_tud_descriptor_configuration_cb(uint8_t index);
uint16_t const *__real_tud_descriptor_string_cb(uint8_t index, uint16_t language_id);

uint8_t const *__wrap_tud_descriptor_device_cb(void)
{
    s_descriptor_reads.device++;
    return __real_tud_descriptor_device_cb();
}

uint8_t const *__wrap_tud_descriptor_configuration_cb(uint8_t index)
{
    s_descriptor_reads.configuration++;
    return __real_tud_descriptor_configuration_cb(index);
}

uint16_t const *__wrap_tud_descriptor_string_cb(uint8_t index, uint16_t language_id)
{
    s_descriptor_reads.string++;
    s_descriptor_reads.string_indexes |= (uint16_t)(1u << (index > 15 ? 15 : index));
    return __real_tud_descriptor_string_cb(index, language_id);
}

deq_usb_descriptor_reads_t deq_usb_device_descriptor_reads(void)
{
    deq_usb_descriptor_reads_t reads = {
        .device = s_descriptor_reads.device,
        .configuration = s_descriptor_reads.configuration,
        .string = s_descriptor_reads.string,
        .string_indexes = s_descriptor_reads.string_indexes,
    };
    return reads;
}

void tud_mount_cb(void)
{
    report(DEQ_USB_EVENT_MOUNTED, s_state.accessory_presented, NULL);
    if (s_state.accessory_presented) {
        s_state.configured = true;
        report(DEQ_USB_EVENT_CONFIGURED, 0, NULL);
    }
}

void tud_umount_cb(void)
{
    s_state.configured = false;
    report(DEQ_USB_EVENT_UNMOUNTED, 0, NULL);
}

void tud_suspend_cb(bool remote_wakeup_enabled)
{
    report(DEQ_USB_EVENT_SUSPENDED, remote_wakeup_enabled, NULL);
}

void tud_resume_cb(void)
{
    report(DEQ_USB_EVENT_RESUMED, 0, NULL);
}

// The received bytes wait in the vendor class's FIFO.
#if CFG_TUD_API_V0_19_COMPAT
void tud_vendor_rx_cb(uint8_t interface, const uint8_t *unused_buffer, uint16_t unused_length)
#else
void tud_vendor_rx_cb(uint8_t interface, const uint8_t *unused_buffer, uint32_t unused_length)
#endif
{
    (void)interface;
    (void)unused_buffer;
    (void)unused_length;
    uint8_t buffer[512];
    uint32_t length;
    while ((length = tud_vendor_read(buffer, sizeof(buffer))) > 0) {
        if (s_state.on_bytes != NULL) {
            s_state.on_bytes(buffer, length);
        }
    }
}

bool deq_usb_device_is_ready(void)
{
    return s_state.configured;
}

bool deq_usb_device_send(const uint8_t *data, size_t length)
{
    if (!s_state.configured) {
        return false;
    }
    // One frame per transfer: write it whole and let it drain before the
    // next frame, so two frames never share a packet.
    size_t sent = 0;
    TickType_t give_up = xTaskGetTickCount() + pdMS_TO_TICKS(1000);
    while (sent < length && xTaskGetTickCount() < give_up) {
        sent += tud_vendor_write(data + sent, length - sent);
        tud_vendor_flush();
        if (sent < length) {
            vTaskDelay(1);
        }
    }
    return sent == length;
}

// Swaps to the accessory identity once START has come. Not done inside the
// control callback: TinyUSB is still finishing that request's status stage.
static void reenumerate_task(void *argument)
{
    (void)argument;
    while (true) {
        if (s_state.start_requested && !s_state.accessory_presented) {
            vTaskDelay(pdMS_TO_TICKS(50));
            tud_disconnect();
            vTaskDelay(pdMS_TO_TICKS(REENUMERATE_DELAY_MS));
            const tinyusb_config_t accessory = {
                .device_descriptor = &s_accessory_device,
                .string_descriptor = s_strings,
                .string_descriptor_count = sizeof(s_strings) / sizeof(s_strings[0]),
                .external_phy = false,
                .configuration_descriptor = s_accessory_config,
            };
            if (tinyusb_set_descriptors(&accessory) != ESP_OK) {
                ESP_LOGE(TAG, "could not switch to the accessory descriptors");
                s_state.start_requested = false;
                tud_connect();
                continue;
            }
            s_state.accessory_presented = true;
            tud_connect();
            report(DEQ_USB_EVENT_ACCESSORY_PRESENTED, ACCESSORY_AUDIO_PRODUCT_ID, NULL);
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

esp_err_t deq_usb_device_start(deq_usb_event_cb_t on_event, deq_usb_bytes_cb_t on_bytes)
{
    memset(&s_state, 0, sizeof(s_state));
    s_state.on_event = on_event;
    s_state.on_bytes = on_bytes;
    const tinyusb_config_t tablet = {
        .device_descriptor = &s_tablet_device,
        .string_descriptor = s_strings,
        .string_descriptor_count = sizeof(s_strings) / sizeof(s_strings[0]),
        .external_phy = false,
        .configuration_descriptor = s_tablet_config,
    };
    esp_err_t installed = tinyusb_driver_install(&tablet);
    if (installed != ESP_OK) {
        return installed;
    }
    if (xTaskCreate(reenumerate_task, "aoa_reenumerate", 4096, NULL, 4, NULL) != pdTRUE) {
        return ESP_FAIL;
    }
    return ESP_OK;
}
