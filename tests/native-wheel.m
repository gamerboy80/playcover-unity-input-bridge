#import <AppKit/AppKit.h>
#include "../src/NativeWheel.h"
#include <assert.h>

int main(void) {
    @autoreleasepool {
        CGEventRef original=CGEventCreateScrollWheelEvent(NULL, kCGScrollEventUnitPixel, 2, 32, -16);
        CGEventSetLocation(original, CGPointMake(100, 200));
        NSEvent *precise=[NSEvent eventWithCGEvent:original];
        assert(precise.hasPreciseScrollingDeltas);
        CGEventRef copy=createNativeWheel((CreateWheel)CGEventCreateScrollWheelEvent, -120, 240);
        CGEventSetLocation(copy, CGEventGetLocation(original));
        NSEvent *wheel=[NSEvent eventWithCGEvent:copy];
        assert(!wheel.hasPreciseScrollingDeltas);
        assert(wheel.scrollingDeltaY==2 && wheel.scrollingDeltaX==-1);
        assert(CGPointEqualToPoint(CGEventGetLocation(copy), CGEventGetLocation(original)));
        assert(CGEventGetIntegerValueField(copy, kCGScrollWheelEventScrollPhase)==0);
        assert(CGEventGetIntegerValueField(copy, kCGScrollWheelEventMomentumPhase)==0);
        assert(CGEventGetIntegerValueField(original, kCGScrollWheelEventIsContinuous)==1);
        NSApplication *app=NSApplication.sharedApplication;
        [app postEvent:wheel atStart:NO];
        NSEvent *queued=[app nextEventMatchingMask:NSEventMaskScrollWheel
            untilDate:[NSDate dateWithTimeIntervalSinceNow:1]
            inMode:NSDefaultRunLoopMode dequeue:YES];
        assert(queued && !queued.hasPreciseScrollingDeltas);
        assert(queued.scrollingDeltaY==2 && queued.scrollingDeltaX==-1);
        CFRelease(copy); CFRelease(original);
    }
}
