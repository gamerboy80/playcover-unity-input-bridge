#ifndef NATIVE_MOUSE_PRESENCE_H
#define NATIVE_MOUSE_PRESENCE_H
#include <stdbool.h>

typedef bool (*MousePresentCallback)(void);

static inline bool installMousePresence(MousePresentCallback *slot,
                                       MousePresentCallback replacement,
                                       MousePresentCallback *original) {
    if (!slot || !*slot || !replacement || *slot==replacement) return false;
    *original=*slot;
    *slot=replacement;
    return true;
}
#endif
