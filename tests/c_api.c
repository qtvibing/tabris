#include <string.h>

#include "tabris.h"

int main(void) {
    const uint8_t pixels[] = {
        255, 0, 0, 255, 0, 255, 0, 255,
        0, 0, 255, 255, 255, 255, 255, 255,
    };
    const uint8_t expected[TABRIS_HASH_SIZE] = {
        0x64, 0x0f, 0x8b, 0x20, 0x0b, 0x0a, 0xce, 0xd0,
        0x60, 0x66, 0xd0, 0x0d, 0x1f, 0x73, 0x3e, 0x26,
    };
    uint8_t output[TABRIS_HASH_SIZE];

    if (!tabris_hash_rgba(pixels, 2, 2, output)) return 1;
    if (memcmp(output, expected, TABRIS_HASH_SIZE) != 0) return 2;
    if (tabris_distance(output, expected) != 0) return 3;
    if (tabris_distance(NULL, expected) != TABRIS_DISTANCE_ERROR) return 4;
    return 0;
}
