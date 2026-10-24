// SPDX-License-Identifier: AGPL-3.0-or-later
//
// The DEQ's frame codec, in plain C with no ESP-IDF in it, so the laptop
// can compile it and test it against the backend's own encoder
// (backend/app/deq_protocol.py). Keep the two in step.
//
// A frame is 0xf0, the 7-byte header 00 40 06 00 00 00 01, the payload
// with each byte split into two nibbles (high first), and 0xf7. A payload
// is little-endian: direction (2), command id (2), length (4, the payload
// length minus 8), transaction id (8), then the body. A reply's body
// starts with STATUS, a signed 32-bit value, zero when the unit took the
// command.
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define DEQ_FRAME_START_MARKER 0xF0
#define DEQ_FRAME_END_MARKER 0xF7
#define DEQ_FRAME_HEADER_BYTES 7
#define DEQ_PAYLOAD_HEADER_BYTES 16
#define DEQ_NOTIFICATION_HEADER_BYTES 8

#define DEQ_DIRECTION_TO_DEVICE 1
#define DEQ_DIRECTION_FROM_DEVICE 2
#define DEQ_DIRECTION_NOTIFICATION 3

#define DEQ_COMMAND_SYNC 0x00
#define DEQ_COMMAND_KEEPALIVE 0x02

// The bytes a frame for a body of `body_length` takes.
size_t deq_frame_size(size_t body_length);

// Writes one frame into `frame`, which holds `frame_capacity` bytes.
// Returns the frame's length, or 0 when it does not fit.
size_t deq_frame_build(uint16_t command_id, uint64_t transaction_id, const uint8_t *body,
                       size_t body_length, uint8_t *frame, size_t frame_capacity);

// What one received frame says.
typedef struct {
    uint16_t direction;
    uint16_t command_id;
    uint64_t transaction_id;  // 0 for a notification, which has none
    bool has_status;          // a reply with at least four body bytes
    int32_t status;
    size_t body_length;
} deq_frame_reply_t;

// Reads one whole frame, from 0xf0 to 0xf7. Returns false when it is not
// a frame this codec can read.
bool deq_frame_parse(const uint8_t *frame, size_t frame_length, deq_frame_reply_t *reply);

// Splits a byte stream into frames. Feed it every received chunk; it calls
// `on_frame` once per whole frame. A frame may arrive in many chunks, and
// one chunk may hold the end of one frame and the start of the next.
typedef void (*deq_frame_found_cb_t)(const uint8_t *frame, size_t frame_length, void *context);

typedef struct {
    uint8_t buffer[8192];
    size_t length;
} deq_frame_joiner_t;

void deq_frame_joiner_reset(deq_frame_joiner_t *joiner);
void deq_frame_joiner_feed(deq_frame_joiner_t *joiner, const uint8_t *chunk, size_t chunk_length,
                           deq_frame_found_cb_t on_frame, void *context);

#ifdef __cplusplus
}
#endif
