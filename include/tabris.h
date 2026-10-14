#ifndef TABRIS_H
#define TABRIS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define TABRIS_HASH_SIZE 16
#define TABRIS_DISTANCE_ERROR UINT8_MAX

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Hashes width * height tightly packed, row-major RGBA8 pixels.
 *
 * Alpha is straight (unassociated). Transparent pixels are composited onto
 * neutral gray. Returns false for null pointers, zero dimensions, or size
 * overflow. The output is untouched on failure.
 */
bool tabris_hash_rgba(
    const uint8_t *pixels,
    size_t width,
    size_t height,
    uint8_t output[TABRIS_HASH_SIZE]
);

/** Returns a Hamming distance in [0, 128], or TABRIS_DISTANCE_ERROR for null. */
uint8_t tabris_distance(
    const uint8_t a[TABRIS_HASH_SIZE],
    const uint8_t b[TABRIS_HASH_SIZE]
);

#ifdef __cplusplus
}
#endif

#endif
