#ifndef ZZZ_NATIVE_WHEEL_H
#define ZZZ_NATIVE_WHEEL_H
#include <stdint.h>
#include <CoreGraphics/CGGeometry.h>
#include "Scroll.h"
#import <Foundation/Foundation.h>

@interface NSObject (ZZZWheelWindowBinding)
- (id)_eventRelativeToWindow:(id)window;
@end

static inline id bindNativeWheelToWindow(id event, id window) {
    if (window && [event respondsToSelector:@selector(_eventRelativeToWindow:)]) {
        return [event _eventRelativeToWindow:window];
    }
    return event;
}

typedef void *(*CreateWheel)(void *, uint32_t, uint32_t, int32_t, ...);

static inline void *createNativeWheel(CreateWheel create, float x, float y) {
    int32_t sx=(int32_t)(x/WheelUnitsPerStep), sy=(int32_t)(y/WheelUnitsPerStep);
    // kCGScrollEventUnitLine=1: create a fresh wheel, with no trackpad gesture metadata.
    return create(NULL, 1, 2, sy, sx);
}
#endif
