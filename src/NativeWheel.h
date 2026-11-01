#ifndef ZZZ_NATIVE_WHEEL_H
#define ZZZ_NATIVE_WHEEL_H
#include <stdint.h>
#include "Scroll.h"

static inline void setNativeWheelFields(void *event,
        void (*setInteger)(void *, uint32_t, int64_t), float x, float y) {
    int64_t sx=(int64_t)(x/WheelUnitsPerStep), sy=(int64_t)(y/WheelUnitsPerStep);
    // Public CGEventField values; preserve the copied event's location/window metadata.
    setInteger(event, 11, sy); setInteger(event, 12, sx);
    setInteger(event, 93, sy*65536); setInteger(event, 94, sx*65536);
    setInteger(event, 96, sy*TrackpadPointsPerStep);
    setInteger(event, 97, sx*TrackpadPointsPerStep);
    setInteger(event, 88, 0); // kCGScrollWheelEventIsContinuous
    setInteger(event, 99, 0); // kCGScrollWheelEventScrollPhase
    setInteger(event, 123, 0); // kCGScrollWheelEventMomentumPhase
}
#endif
