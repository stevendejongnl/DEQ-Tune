// SPDX-License-Identifier: AGPL-3.0-or-later
//
// The link probe: does this ESP32-S3 hold a conversation with a real DEQ?
//
// It walks the stages a working link takes, the same ones the Pi took,
// and records how far it got:
//
//   1 bus      a host reset the bus and talks to the board
//   2 aoa      the host asked for the AOA protocol (answered: 2)
//   3 strings  six identification strings and SET_AUDIO_MODE arrived
//   4 start    START came, and the board re-enumerated as 18d1:2d04
//   5 config   the host configured the accessory
//   6 sync     COMMAND_SYNC drew a reply with STATUS 0
//   7 hold     the DEQ answered keepalives for HOLD_STAGE_SECONDS
//
// It sends only what the Pi gadget sends on its own: COMMAND_SYNC with the
// app's 24 bytes, the read-only cold start, and keepalives. It writes
// nothing to the unit's settings.
//
// The result goes three ways, so a car session needs no laptop:
//   - the RGB LED shows the stage reached (see stage_colour)
//   - flash (NVS) keeps one record per boot for the last RECORD_SLOTS
//     boots, and each boot prints the ones before it
//   - UART0, the board's COM port, logs every step live
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "deq_frame.h"
#include "deq_usb_device.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "led_strip.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "tusb.h"

static const char *TAG = "probe";

#define NVS_NAMESPACE "deqprobe"
#define HOLD_STAGE_SECONDS 60
// The app sends a keepalive every nine seconds for the whole session.
#define KEEPALIVE_SECONDS 9
#define REPLY_WAIT_MS 2000
#define COLD_START_GAP_MS 100
// A car session can power the board up several times. Each boot keeps
// its own record, so a later boot does not overwrite the one that shows
// the problem.
#define RECORD_SLOTS 8
#define ALIVE_SAVE_SECONDS 10

typedef enum {
    STAGE_NONE = 0,
    STAGE_BUS,
    STAGE_AOA,
    STAGE_STRINGS,
    STAGE_START,
    STAGE_CONFIGURED,
    STAGE_SYNC,
    STAGE_HOLD,
} stage_t;

static const char *STAGE_NAMES[] = {"none", "bus", "aoa", "strings", "start", "config", "sync", "hold"};

// The app's own COMMAND_SYNC body (b/e/b.h()). The DEQ refuses a bodyless
// one with STATUS -5 and then ignores every frame after it.
static const uint8_t SYNC_BODY[] = {0xa5, 0xc5, 0x43, 0x84, 0x7b, 0x35, 0x6c, 0x8c, 0x40, 0x8b, 0x70, 0x16,
                                    0x79, 0xce, 0x1f, 0x11, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};

// The read-only part of the app's cold start, as pi-gadget sends it.
typedef struct {
    uint16_t command_id;
    uint8_t body[4];
    uint8_t body_length;
} cold_start_read_t;

static const cold_start_read_t COLD_START_READS[] = {
    {0x21, {0x10, 0x27, 0x00, 0x00}, 4},  // SET_TIMEOUT_INTERVAL 10000
    {0x17, {0}, 0},                       // GET_SYSTEM_ERROR_FLAGS
    {0x15, {0}, 0},                       // GET_CRASH_REPORT
    {0x03, {0}, 0},                       // GET_VERSION
    {0x04, {0}, 0},                       // GET_HW_INFORMATION
    {0x0A, {0}, 0},                       // GET_USER_LOG
    {0x20, {0}, 0},                       // GET_USB_CONDITIONER_CONFIGURATION_TABLE
    {0x09, {0}, 0},                       // READ_USER_CONFIGURATION
    {0x06, {0x00, 0x00, 0x00, 0x00}, 4},  // GET_OPAL_CONFIGURATION 0
};

// What this boot saw. The USB callbacks write it, the probe task reads it.
typedef struct {
    volatile stage_t stage;
    volatile uint32_t strings;
    volatile uint32_t audio_mode;
    volatile uint32_t unhandled_request;
    volatile uint32_t replies_ok;
    volatile uint32_t replies_refused;
    volatile uint32_t notifications;
    volatile uint32_t unanswered_keepalives;
    volatile int32_t last_refusal;
    volatile uint16_t last_refused_command;
    volatile bool sync_answered;
    volatile int32_t sync_status;
    volatile uint16_t mounts;
    volatile uint16_t suspends;
    volatile uint16_t resumes;
    volatile uint16_t unmounts;
    volatile bool changed;
    uint32_t bus_at_ms;
    uint32_t held_s;
    char manufacturer[64];
    char model[64];
} session_t;

// One boot's record in flash. The layout is fixed: a firmware change that
// changes it must change RECORD_VERSION, so old records read as empty.
#define RECORD_VERSION 3
typedef struct {
    uint8_t version;
    uint8_t reset_reason;
    uint8_t stage;
    uint8_t strings;
    uint32_t boot;
    uint32_t alive_s;
    uint32_t bus_at_ms;
    uint16_t mounts;
    uint16_t suspends;
    uint16_t resumes;
    uint16_t unmounts;
    uint16_t device_reads;
    uint16_t configuration_reads;
    uint16_t string_reads;
    uint16_t string_indexes;
    uint32_t audio_mode;
    uint32_t unhandled_request;
    uint32_t held_s;
    uint32_t replies_ok;
    uint32_t replies_refused;
    uint32_t unanswered_keepalives;
    uint32_t notifications;
    int32_t sync_status;
    int32_t last_refusal;
    uint16_t last_refused_command;
    char manufacturer[24];
    char model[24];
    deq_usb_trace_t trace;
} boot_record_t;

static session_t s_session;
static uint32_t s_boot;
static led_strip_handle_t s_led;
static deq_frame_joiner_t s_joiner;

// ---------------------------------------------------------------------
// LED: one colour per stage, red for a refusal
// ---------------------------------------------------------------------

static void stage_colour(stage_t stage, uint8_t *red, uint8_t *green, uint8_t *blue)
{
    static const uint8_t COLOURS[][3] = {
        {0, 0, 8},    // none: dim blue, waiting for a host
        {0, 0, 40},   // bus: blue
        {20, 0, 40},  // aoa: purple
        {40, 0, 40},  // strings: magenta
        {40, 20, 0},  // start: orange
        {40, 40, 0},  // config: yellow
        {0, 40, 20},  // sync: teal
        {0, 40, 0},   // hold: green, the link works
    };
    *red = COLOURS[stage][0];
    *green = COLOURS[stage][1];
    *blue = COLOURS[stage][2];
}

static void show_stage(void)
{
    if (s_led == NULL) {
        return;
    }
    uint8_t red, green, blue;
    stage_colour(s_session.stage, &red, &green, &blue);
    if (s_session.replies_refused > 0) {
        red = 40, green = 0, blue = 0;
    }
    led_strip_set_pixel(s_led, 0, red, green, blue);
    led_strip_refresh(s_led);
}

static void reach(stage_t stage)
{
    if (stage > s_session.stage) {
        s_session.stage = stage;
        ESP_LOGI(TAG, "stage %d: %s", stage, STAGE_NAMES[stage]);
    }
}

// ---------------------------------------------------------------------
// The report in flash
// ---------------------------------------------------------------------

static void record_key(uint32_t boot, char *key, size_t key_size)
{
    snprintf(key, key_size, "boot%u", (unsigned)(boot % RECORD_SLOTS));
}

static void save_report(void)
{
    deq_usb_descriptor_reads_t reads = deq_usb_device_descriptor_reads();
    boot_record_t record = {
        .device_reads = reads.device,
        .configuration_reads = reads.configuration,
        .string_reads = reads.string,
        .string_indexes = reads.string_indexes,
        .version = RECORD_VERSION,
        .reset_reason = (uint8_t)esp_reset_reason(),
        .stage = (uint8_t)s_session.stage,
        .strings = (uint8_t)s_session.strings,
        .boot = s_boot,
        .alive_s = (uint32_t)(esp_timer_get_time() / 1000000),
        .bus_at_ms = s_session.bus_at_ms,
        .mounts = s_session.mounts,
        .suspends = s_session.suspends,
        .resumes = s_session.resumes,
        .unmounts = s_session.unmounts,
        .audio_mode = s_session.audio_mode,
        .unhandled_request = s_session.unhandled_request,
        .held_s = s_session.held_s,
        .replies_ok = s_session.replies_ok,
        .replies_refused = s_session.replies_refused,
        .unanswered_keepalives = s_session.unanswered_keepalives,
        .notifications = s_session.notifications,
        .sync_status = s_session.sync_answered ? s_session.sync_status : INT32_MIN,
        .last_refusal = s_session.last_refusal,
        .last_refused_command = s_session.last_refused_command,
    };
    deq_usb_device_trace(&record.trace);
    strlcpy(record.manufacturer, s_session.manufacturer, sizeof(record.manufacturer));
    strlcpy(record.model, s_session.model, sizeof(record.model));

    nvs_handle_t storage;
    if (nvs_open(NVS_NAMESPACE, NVS_READWRITE, &storage) != ESP_OK) {
        return;
    }
    char key[16];
    record_key(s_boot, key, sizeof(key));
    nvs_set_blob(storage, key, &record, sizeof(record));
    nvs_commit(storage);
    nvs_close(storage);
}

static const char *reset_reason_name(uint8_t reason)
{
    switch ((esp_reset_reason_t)reason) {
    case ESP_RST_POWERON: return "poweron";
    case ESP_RST_EXT: return "external";
    case ESP_RST_SW: return "software";
    case ESP_RST_PANIC: return "panic";
    case ESP_RST_INT_WDT: return "interrupt-watchdog";
    case ESP_RST_TASK_WDT: return "task-watchdog";
    case ESP_RST_WDT: return "watchdog";
    case ESP_RST_DEEPSLEEP: return "deepsleep";
    case ESP_RST_BROWNOUT: return "brownout";
    case ESP_RST_SDIO: return "sdio";
    case ESP_RST_USB: return "usb";
    case ESP_RST_JTAG: return "jtag";
    default: return "unknown";
    }
}

// Prints the trace four entries to a line: a SETUP packet as its 8 bytes
// in hex, a bus event by name.
static void print_trace(const deq_usb_trace_t *trace)
{
    static const char *BUS_EVENTS[] = {"?", "RESET", "UNPLUGGED", "?", "SUSPEND", "RESUME"};
    char line[160];
    size_t used = 0;
    uint8_t count = trace->count > DEQ_USB_TRACE_ENTRIES ? DEQ_USB_TRACE_ENTRIES : trace->count;
    for (uint8_t index = 0; index < count; index++) {
        const uint8_t *entry = trace->entries[index];
        if (entry[0] == DEQ_USB_TRACE_BUS_EVENT) {
            used += snprintf(line + used, sizeof(line) - used, " %s", entry[1] <= 5 ? BUS_EVENTS[entry[1]] : "?");
        } else {
            used += snprintf(line + used, sizeof(line) - used, " %02x%02x:%02x%02x:%02x%02x:%02x%02x", entry[0],
                             entry[1], entry[3], entry[2], entry[5], entry[4], entry[7], entry[6]);
        }
        if (index % 4 == 3 || index == count - 1) {
            ESP_LOGI(TAG, "REPORT   trace%s", line);
            used = 0;
        }
    }
}

static void print_record(const boot_record_t *record)
{
    uint8_t stage = record->stage > STAGE_HOLD ? STAGE_NONE : record->stage;
    ESP_LOGI(TAG,
             "REPORT boot=%" PRIu32 " reset=%s alive_s=%" PRIu32 " stage=%u(%s) bus_at_ms=%" PRIu32
             " mounts=%u suspends=%u resumes=%u unmounts=%u",
             record->boot, reset_reason_name(record->reset_reason), record->alive_s, stage, STAGE_NAMES[stage],
             record->bus_at_ms, record->mounts, record->suspends, record->resumes, record->unmounts);
    ESP_LOGI(TAG, "REPORT   reads: device=%u configuration=%u string=%u string_indexes=0x%04x", record->device_reads,
             record->configuration_reads, record->string_reads, record->string_indexes);
    print_trace(&record->trace);
    if (stage < STAGE_AOA) {
        return;
    }
    ESP_LOGI(TAG,
             "REPORT   host=\"%s\" model=\"%s\" strings=%u audio_mode=%" PRIu32 " unhandled_request=%" PRIu32,
             record->manufacturer, record->model, record->strings, record->audio_mode, record->unhandled_request);
    if (stage < STAGE_CONFIGURED) {
        return;
    }
    if (record->sync_status == INT32_MIN) {
        ESP_LOGI(TAG, "REPORT   sync=no-reply");
    } else {
        ESP_LOGI(TAG, "REPORT   sync_status=%" PRId32, record->sync_status);
    }
    ESP_LOGI(TAG,
             "REPORT   held_s=%" PRIu32 " replies_ok=%" PRIu32 " refused=%" PRIu32 " last_refusal=%" PRId32
             " on 0x%02x unanswered_keepalives=%" PRIu32 " notifications=%" PRIu32,
             record->held_s, record->replies_ok, record->replies_refused, record->last_refusal,
             record->last_refused_command, record->unanswered_keepalives, record->notifications);
}

// Counts this boot and prints the records of the boots before it, oldest
// first. Opening the COM port resets the board, so this is what a laptop
// sees first.
static void print_earlier_boots(void)
{
    nvs_handle_t storage;
    if (nvs_open(NVS_NAMESPACE, NVS_READWRITE, &storage) != ESP_OK) {
        return;
    }
    nvs_get_u32(storage, "boots", &s_boot);
    nvs_set_u32(storage, "boots", s_boot + 1);
    nvs_commit(storage);

    uint32_t first = s_boot > RECORD_SLOTS ? s_boot - RECORD_SLOTS : 0;
    for (uint32_t boot = first; boot < s_boot; boot++) {
        char key[16];
        record_key(boot, key, sizeof(key));
        boot_record_t record;
        size_t length = sizeof(record);
        if (nvs_get_blob(storage, key, &record, &length) != ESP_OK || length != sizeof(record) ||
            record.version != RECORD_VERSION || record.boot != boot) {
            continue;
        }
        print_record(&record);
    }
    ESP_LOGI(TAG, "REPORT this boot is %" PRIu32, s_boot);
    nvs_close(storage);
}

// ---------------------------------------------------------------------
// USB events and received frames
// ---------------------------------------------------------------------

static void on_usb_event(deq_usb_event_t event, uint32_t value, const char *text)
{
    switch (event) {
    case DEQ_USB_EVENT_BUS_RESET:
        reach(STAGE_BUS);
        break;
    case DEQ_USB_EVENT_GET_PROTOCOL:
        reach(STAGE_AOA);
        ESP_LOGI(TAG, "GET_PROTOCOL, answered %" PRIu32, value);
        break;
    case DEQ_USB_EVENT_STRING:
        s_session.strings++;
        ESP_LOGI(TAG, "string %" PRIu32 ": \"%s\"", value, text);
        if (value == 0) {
            strlcpy(s_session.manufacturer, text, sizeof(s_session.manufacturer));
        } else if (value == 1) {
            strlcpy(s_session.model, text, sizeof(s_session.model));
        }
        break;
    case DEQ_USB_EVENT_AUDIO_MODE:
        s_session.audio_mode = value;
        ESP_LOGI(TAG, "SET_AUDIO_MODE %" PRIu32, value);
        if (s_session.strings >= 6) {
            reach(STAGE_STRINGS);
        }
        break;
    case DEQ_USB_EVENT_START:
        if (s_session.strings >= 6) {
            reach(STAGE_STRINGS);
        }
        ESP_LOGI(TAG, "START");
        break;
    case DEQ_USB_EVENT_ACCESSORY_PRESENTED:
        reach(STAGE_START);
        ESP_LOGI(TAG, "re-enumerated as 18d1:%04" PRIx32, value);
        break;
    case DEQ_USB_EVENT_CONFIGURED:
        reach(STAGE_CONFIGURED);
        break;
    case DEQ_USB_EVENT_AUDIO_ALTERNATE:
        ESP_LOGI(TAG, "audio alternate %" PRIu32, value);
        break;
    case DEQ_USB_EVENT_UNMOUNTED:
        s_session.unmounts++;
        s_session.changed = true;
        ESP_LOGW(TAG, "the host went away");
        break;
    case DEQ_USB_EVENT_MOUNTED:
        s_session.mounts++;
        s_session.changed = true;
        ESP_LOGI(TAG, "configured by the host (%s)", value ? "accessory" : "tablet");
        break;
    case DEQ_USB_EVENT_SUSPENDED:
        s_session.suspends++;
        s_session.changed = true;
        ESP_LOGI(TAG, "bus suspended");
        break;
    case DEQ_USB_EVENT_RESUMED:
        s_session.resumes++;
        s_session.changed = true;
        ESP_LOGI(TAG, "bus resumed");
        break;
    case DEQ_USB_EVENT_UNHANDLED_REQUEST:
        s_session.unhandled_request = value;
        ESP_LOGW(TAG, "unhandled control request %" PRIu32, value);
        break;
    }
}

static void on_frame(const uint8_t *frame, size_t length, void *context)
{
    (void)context;
    deq_frame_reply_t reply;
    if (!deq_frame_parse(frame, length, &reply)) {
        ESP_LOGW(TAG, "a frame of %u bytes that does not parse", (unsigned)length);
        return;
    }
    if (reply.direction == DEQ_DIRECTION_NOTIFICATION) {
        s_session.notifications++;
        ESP_LOGI(TAG, "notification 0x%02x", reply.command_id);
        return;
    }
    int32_t status = reply.has_status ? reply.status : 0;
    if (reply.command_id == DEQ_COMMAND_SYNC) {
        s_session.sync_answered = true;
        s_session.sync_status = status;
    }
    if (status == 0) {
        s_session.replies_ok++;
    } else {
        s_session.replies_refused++;
        s_session.last_refusal = status;
        s_session.last_refused_command = reply.command_id;
    }
    ESP_LOGI(TAG, "reply 0x%02x id %" PRIu64 " STATUS %" PRId32 " (%u body bytes)", reply.command_id,
             reply.transaction_id, status, (unsigned)reply.body_length);
}

static void on_usb_bytes(const uint8_t *data, size_t length)
{
    deq_frame_joiner_feed(&s_joiner, data, length, on_frame, NULL);
}

// ---------------------------------------------------------------------
// The conversation
// ---------------------------------------------------------------------

static bool send_command(uint16_t command_id, uint64_t transaction_id, const uint8_t *body, size_t body_length)
{
    static uint8_t frame[256];
    size_t length = deq_frame_build(command_id, transaction_id, body, body_length, frame, sizeof(frame));
    if (length == 0 || !deq_usb_device_send(frame, length)) {
        ESP_LOGW(TAG, "could not send 0x%02x", command_id);
        return false;
    }
    ESP_LOGI(TAG, "sent 0x%02x id %" PRIu64, command_id, transaction_id);
    return true;
}

static void converse(void)
{
    uint64_t transaction_id = 1;
    vTaskDelay(pdMS_TO_TICKS(300));
    send_command(DEQ_COMMAND_SYNC, transaction_id++, SYNC_BODY, sizeof(SYNC_BODY));
    for (int waited = 0; waited < REPLY_WAIT_MS && !s_session.sync_answered; waited += 20) {
        vTaskDelay(pdMS_TO_TICKS(20));
    }
    if (!s_session.sync_answered) {
        ESP_LOGW(TAG, "no reply to COMMAND_SYNC within %d ms", REPLY_WAIT_MS);
    } else if (s_session.sync_status == 0) {
        reach(STAGE_SYNC);
    }
    show_stage();
    for (size_t index = 0; index < sizeof(COLD_START_READS) / sizeof(COLD_START_READS[0]); index++) {
        vTaskDelay(pdMS_TO_TICKS(COLD_START_GAP_MS));
        const cold_start_read_t *read = &COLD_START_READS[index];
        send_command(read->command_id, transaction_id++, read->body, read->body_length);
    }
    // The link counts as held only up to the last keepalive that drew a
    // reply. A host that keeps the device configured and stops answering
    // (a laptop, or a wedged unit) must not look like a working link.
    int64_t linked_at = esp_timer_get_time();
    uint32_t held = 0;
    while (deq_usb_device_is_ready()) {
        vTaskDelay(pdMS_TO_TICKS(KEEPALIVE_SECONDS * 1000));
        if (!deq_usb_device_is_ready()) {
            break;
        }
        uint32_t replies_before = s_session.replies_ok + s_session.replies_refused;
        send_command(DEQ_COMMAND_KEEPALIVE, transaction_id, NULL, 0);
        transaction_id = transaction_id % 0xFF + 1;
        for (int waited = 0; waited < REPLY_WAIT_MS && s_session.replies_ok + s_session.replies_refused == replies_before;
             waited += 20) {
            vTaskDelay(pdMS_TO_TICKS(20));
        }
        if (s_session.replies_ok + s_session.replies_refused == replies_before) {
            s_session.unanswered_keepalives++;
            ESP_LOGW(TAG, "no reply to the keepalive");
        } else {
            held = (uint32_t)((esp_timer_get_time() - linked_at) / 1000000);
        }
        if (held >= HOLD_STAGE_SECONDS && s_session.stage == STAGE_SYNC) {
            reach(STAGE_HOLD);
        }
        s_session.held_s = held;
        save_report();
        show_stage();
    }
    ESP_LOGW(TAG, "the link ended");
}

static void start_led(void)
{
    led_strip_config_t strip = {
        .strip_gpio_num = CONFIG_PROBE_LED_GPIO,
        .max_leds = 1,
    };
    led_strip_rmt_config_t rmt = {
        .resolution_hz = 10 * 1000 * 1000,
    };
    if (led_strip_new_rmt_device(&strip, &rmt, &s_led) != ESP_OK) {
        ESP_LOGW(TAG, "no LED on GPIO %d", CONFIG_PROBE_LED_GPIO);
        s_led = NULL;
    }
}

void app_main(void)
{
    esp_err_t flash = nvs_flash_init();
    if (flash == ESP_ERR_NVS_NO_FREE_PAGES || flash == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }
    memset(&s_session, 0, sizeof(s_session));
    print_earlier_boots();
    deq_frame_joiner_reset(&s_joiner);
    start_led();
    show_stage();
    ESP_ERROR_CHECK(deq_usb_device_start(on_usb_event, on_usb_bytes));
    ESP_LOGI(TAG, "waiting for a host on the USB-OTG port");

    // The first record says that this boot happened, even when the board
    // loses power before a host shows up.
    save_report();
    stage_t shown = STAGE_NONE;
    deq_usb_descriptor_reads_t saved_reads = deq_usb_device_descriptor_reads();
    uint8_t saved_trace_count = 0;
    int64_t saved_at = esp_timer_get_time();
    while (true) {
        if (tud_connected() && s_session.stage < STAGE_BUS) {
            s_session.bus_at_ms = (uint32_t)(esp_timer_get_time() / 1000);
            reach(STAGE_BUS);
        }
        bool alive_due = esp_timer_get_time() - saved_at >= ALIVE_SAVE_SECONDS * 1000000LL;
        deq_usb_descriptor_reads_t reads = deq_usb_device_descriptor_reads();
        deq_usb_trace_t trace;
        deq_usb_device_trace(&trace);
        bool reads_changed = memcmp(&reads, &saved_reads, sizeof(reads)) != 0 || trace.count != saved_trace_count;
        saved_trace_count = trace.count;
        if (s_session.stage != shown || s_session.changed || reads_changed || alive_due) {
            saved_reads = reads;
            shown = s_session.stage;
            s_session.changed = false;
            show_stage();
            save_report();
            saved_at = esp_timer_get_time();
        }
        if (deq_usb_device_is_ready()) {
            converse();
            save_report();
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}
