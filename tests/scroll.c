#include "../src/Scroll.h"
#include "../src/InputState.h"
#include <assert.h>

int main(void) {
    double remainder=0;
    assert(unityScroll(&remainder, 1, 0) == 120);
    assert(unityScroll(&remainder, -2, 0) == -240);
    assert(unityScroll(&remainder, 0, 0) == 0);
    assert(remainder == 0);
    assert(unityScroll(&remainder, 5.25, 1) == 0);
    assert(unityScroll(&remainder, 10.75, 1) == 120);
    assert(remainder == 0);
    assert(unityScroll(&remainder, 35, 1) == 240);
    assert(remainder == 3);
    assert(unityScroll(&remainder, -19, 1) == -120);
    assert(remainder == 0);
    assert(unityScroll(&remainder, -7, 1) == 0);
    assert(unityScroll(&remainder, 7, 1) == 0);
    assert(remainder == 0);
    assert(unityScroll(&remainder, NAN, 1) == 0);
    MouseState mouse = {.sx=30, .sy=-120, .buttons=3};
    uint8_t state[MaxDeviceStateBytes];
    memset(state, 0xff, sizeof(state));
    assert(packMouseState(state, &mouse, 49) == 49);
    assert(memcmp(state, &mouse, sizeof(mouse)) == 0);
    for (size_t i=sizeof(mouse); i<sizeof(state); ++i) assert(state[i] == 0);
    assert(packMouseState(state, &mouse, 30) == 30);
    assert(packMouseState(state, &mouse, 29) == 0);
    assert(packMouseState(state, &mouse, 65) == 0);
}
