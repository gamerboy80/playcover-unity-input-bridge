#ifndef ZZZ_SCROLL_H
#define ZZZ_SCROLL_H
#include <math.h>

enum { TrackpadPointsPerStep = 16, WheelUnitsPerStep = 120 };

static inline float unityScroll(double *remainder, double delta, int precise) {
    if (!isfinite(delta)) return 0;
    if (!precise) return (float)(delta * WheelUnitsPerStep);
    *remainder += delta;
    double steps = trunc(*remainder / TrackpadPointsPerStep);
    *remainder -= steps * TrackpadPointsPerStep;
    return (float)(steps * WheelUnitsPerStep);
}

#endif
