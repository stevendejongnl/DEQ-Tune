// SPDX-License-Identifier: AGPL-3.0-or-later
#include "deq_frame.h"

#include <string.h>

static const uint8_t FRAME_HEADER[DEQ_FRAME_HEADER_BYTES] = {0x00, 0x40, 0x06, 0x00, 0x00, 0x00, 0x01};
// The length field counts the payload from the transaction id onwards.
#define LENGTH_FIELD_BIAS 8
// A frame whose size is an exact multiple of this gets one extra 0x00.
// With this unit's 7-byte header a frame is always odd in size, so the
// rule never fires. The backend keeps it, so this codec does too.
#define FRAME_PAD_MULTIPLE 512

static void write_little_endian(uint8_t *target, uint64_t value, size_t bytes)
{
    for (size_t index = 0; index < bytes; index++) {
        target[index] = (uint8_t)(value >> (8 * index));
    }
}

static uint64_t read_little_endian(const uint8_t *source, size_t bytes)
{
    uint64_t value = 0;
    for (size_t index = 0; index < bytes; index++) {
        value |= (uint64_t)source[index] << (8 * index);
    }
    return value;
}

size_t deq_frame_size(size_t body_length)
{
    size_t size = 1 + DEQ_FRAME_HEADER_BYTES + 2 * (DEQ_PAYLOAD_HEADER_BYTES + body_length) + 1;
    return size % FRAME_PAD_MULTIPLE == 0 ? size + 1 : size;
}

size_t deq_frame_build(uint16_t command_id, uint64_t transaction_id, const uint8_t *body,
                       size_t body_length, uint8_t *frame, size_t frame_capacity)
{
    size_t size = deq_frame_size(body_length);
    if (size > frame_capacity) {
        return 0;
    }
    uint8_t header[DEQ_PAYLOAD_HEADER_BYTES];
    write_little_endian(&header[0], DEQ_DIRECTION_TO_DEVICE, 2);
    write_little_endian(&header[2], command_id, 2);
    write_little_endian(&header[4], DEQ_PAYLOAD_HEADER_BYTES + body_length - LENGTH_FIELD_BIAS, 4);
    write_little_endian(&header[8], transaction_id, 8);

    size_t position = 0;
    frame[position++] = DEQ_FRAME_START_MARKER;
    memcpy(&frame[position], FRAME_HEADER, DEQ_FRAME_HEADER_BYTES);
    position += DEQ_FRAME_HEADER_BYTES;
    for (size_t index = 0; index < DEQ_PAYLOAD_HEADER_BYTES + body_length; index++) {
        uint8_t payload_byte = index < DEQ_PAYLOAD_HEADER_BYTES ? header[index]
                                                                : body[index - DEQ_PAYLOAD_HEADER_BYTES];
        frame[position++] = (payload_byte >> 4) & 0x0F;
        frame[position++] = payload_byte & 0x0F;
    }
    frame[position++] = DEQ_FRAME_END_MARKER;
    if (position < size) {
        frame[position++] = 0x00;
    }
    return position;
}

// Reads the payload byte at `index` from the nibble pairs.
static uint8_t payload_byte_at(const uint8_t *nibbles, size_t index)
{
    return (uint8_t)((nibbles[2 * index] << 4) | (nibbles[2 * index + 1] & 0x0F));
}

bool deq_frame_parse(const uint8_t *frame, size_t frame_length, deq_frame_reply_t *reply)
{
    if (frame_length < 2 + DEQ_FRAME_HEADER_BYTES || frame[0] != DEQ_FRAME_START_MARKER) {
        return false;
    }
    size_t end = frame_length - 1;
    if (frame[end] == 0x00 && end > 0) {
        end--;  // the pad byte
    }
    if (frame[end] != DEQ_FRAME_END_MARKER) {
        return false;
    }
    const uint8_t *nibbles = &frame[1 + DEQ_FRAME_HEADER_BYTES];
    size_t nibble_count = end - (1 + DEQ_FRAME_HEADER_BYTES);
    if (nibble_count % 2 != 0) {
        return false;
    }
    size_t payload_length = nibble_count / 2;
    if (payload_length < DEQ_NOTIFICATION_HEADER_BYTES) {
        return false;
    }
    uint8_t header[DEQ_PAYLOAD_HEADER_BYTES] = {0};
    size_t header_length = payload_length < DEQ_PAYLOAD_HEADER_BYTES ? payload_length : DEQ_PAYLOAD_HEADER_BYTES;
    for (size_t index = 0; index < header_length; index++) {
        header[index] = payload_byte_at(nibbles, index);
    }
    memset(reply, 0, sizeof(*reply));
    reply->direction = (uint16_t)read_little_endian(&header[0], 2);
    reply->command_id = (uint16_t)read_little_endian(&header[2], 2);
    // A notification carries no transaction id: its body starts at byte 8.
    size_t body_offset = reply->direction == DEQ_DIRECTION_NOTIFICATION ? DEQ_NOTIFICATION_HEADER_BYTES
                                                                       : DEQ_PAYLOAD_HEADER_BYTES;
    if (payload_length < body_offset) {
        return false;
    }
    if (body_offset == DEQ_PAYLOAD_HEADER_BYTES) {
        reply->transaction_id = read_little_endian(&header[8], 8);
    }
    reply->body_length = payload_length - body_offset;
    if (reply->direction == DEQ_DIRECTION_FROM_DEVICE && reply->body_length >= 4) {
        uint8_t status[4];
        for (size_t index = 0; index < 4; index++) {
            status[index] = payload_byte_at(nibbles, body_offset + index);
        }
        reply->has_status = true;
        reply->status = (int32_t)(uint32_t)read_little_endian(status, 4);
    }
    return true;
}

void deq_frame_joiner_reset(deq_frame_joiner_t *joiner)
{
    joiner->length = 0;
}

void deq_frame_joiner_feed(deq_frame_joiner_t *joiner, const uint8_t *chunk, size_t chunk_length,
                           deq_frame_found_cb_t on_frame, void *context)
{
    for (size_t index = 0; index < chunk_length; index++) {
        uint8_t received = chunk[index];
        if (received == DEQ_FRAME_START_MARKER) {
            joiner->length = 0;  // a new frame starts; drop any broken rest
        }
        if (joiner->length == 0 && received != DEQ_FRAME_START_MARKER) {
            continue;  // bytes between frames, such as a pad byte
        }
        if (joiner->length >= sizeof(joiner->buffer)) {
            joiner->length = 0;  // too long to be a frame; start over
            continue;
        }
        joiner->buffer[joiner->length++] = received;
        if (received == DEQ_FRAME_END_MARKER) {
            on_frame(joiner->buffer, joiner->length, context);
            joiner->length = 0;
        }
    }
}
