#ifndef ZZZ_INPUT_STATE_H
#define ZZZ_INPUT_STATE_H
#include <stddef.h>
#include <stdint.h>
#include <string.h>

typedef struct __attribute__((packed)) {
    uint32_t type;
    uint16_t size, device;
    double time;
    uint32_t eventID, format;
} StateHeader;

typedef struct __attribute__((packed)) {
    float x, y, dx, dy, sx, sy;
    uint16_t buttons, display, clicks;
} MouseState;

enum { MaxDeviceStateBytes = 64 };
_Static_assert(sizeof(StateHeader) == 24, "Unity StateEvent header");
_Static_assert(offsetof(StateHeader, time) == 8, "Unity event timestamp");
_Static_assert(sizeof(MouseState) == 30, "Standard MouseState prefix");

static inline size_t packMouseState(uint8_t *result, const MouseState *state, size_t size) {
    if (size < sizeof(*state) || size > MaxDeviceStateBytes) return 0;
    memset(result, 0, MaxDeviceStateBytes);
    memcpy(result, state, sizeof(*state));
    return size;
}
#endif
