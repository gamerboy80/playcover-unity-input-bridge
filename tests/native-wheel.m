#import <AppKit/AppKit.h>
#include "../src/NativeWheel.h"
#include "../src/Capture.h"
#include <assert.h>

@interface WheelTestView : NSView
@property NSInteger received;
@end
@implementation WheelTestView
- (void)scrollWheel:(NSEvent *)event {
    assert(!event.hasPreciseScrollingDeltas);
    assert(event.scrollingDeltaY==2 && event.scrollingDeltaX==-1);
    self.received++;
}
@end

static int cursorDepth=2; // Simulate hide ownership held by another component.
static void testHide(void) { cursorDepth++; }
static void testUnhide(void) { cursorDepth--; }

int main(void) {
    @autoreleasepool {
        unsigned owned=0;
        balanceCursorHide(&owned,true,true,testHide,testUnhide);
        assert(owned==1 && cursorDepth==3);
        for (int i=0;i<100;i++) balanceCursorHide(&owned,true,true,testHide,testUnhide);
        assert(owned==1 && cursorDepth==3); // Re-hiding must not accumulate a depth of 101.
        balanceCursorHide(&owned,true,false,testHide,testUnhide);
        assert(owned==1 && cursorDepth==3);
        balanceCursorHide(&owned,false,false,testHide,testUnhide);
        assert(owned==0 && cursorDepth==2); // Release only our own hide claim.
        balanceCursorHide(&owned,false,true,testHide,testUnhide);
        assert(cursorDepth==2);
        bool first=true;
        assert(!captureMotionReady(&first,5,1)); // First movement may arrive long after capture.
        assert(captureMotionReady(&first,6,1));
        first=true;
        assert(!captureMotionReady(&first,0,1));
        assert(!captureMotionReady(&first,.5,1));
        assert(captureMotionReady(&first,1,1));
        CGRect content=CGRectMake(10,20,300,200);
        assert(cursorInsideContent(CGPointMake(100,100),content));
        assert(!cursorInsideContent(CGPointMake(100,-10),content)); // Dock, below window.
        assert(!cursorInsideContent(CGPointMake(-100,100),content));
        assert(!cursorInsideContent(CGPointMake(310,220),content));
        assert(!cursorInsideContent(CGPointZero,CGRectZero));
        assert(CGPointEqualToPoint(captureScreenPoint(CGPointMake(300,200),900),CGPointMake(300,700)));
        // Other displays may be left of or above the primary display.
        assert(CGPointEqualToPoint(captureScreenPoint(CGPointMake(-500,1200),900),CGPointMake(-500,-300)));
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
        NSWindow *window=[[NSWindow alloc] initWithContentRect:NSMakeRect(100,100,300,200)
            styleMask:NSWindowStyleMaskBorderless backing:NSBackingStoreBuffered defer:NO];
        if (window.windowNumber>0) {
            WheelTestView *view=[[WheelTestView alloc] initWithFrame:NSMakeRect(0,0,300,200)];
            window.contentView=view;
            CGPoint point=[window convertPointToScreen:CGPointMake(50,50)];
            point.y=NSScreen.screens.firstObject.frame.size.height-point.y;
            CGEventSetLocation(copy,point);
            wheel=[NSEvent eventWithCGEvent:copy];
            assert(wheel.windowNumber==0);
            wheel=bindNativeWheelToWindow(wheel, window);
            assert(wheel.window==window && wheel.windowNumber==window.windowNumber);
            assert(!wheel.hasPreciseScrollingDeltas);
            dispatchNativeWheelToWindow(wheel,window);
            assert(view.received==1);
        } else {
            fprintf(stderr,"SKIP: Window binding needs WindowServer access\n");
        }
        [app postEvent:wheel atStart:NO];
        NSEvent *queued=[app nextEventMatchingMask:NSEventMaskScrollWheel
            untilDate:[NSDate dateWithTimeIntervalSinceNow:1]
            inMode:NSDefaultRunLoopMode dequeue:YES];
        assert(queued && !queued.hasPreciseScrollingDeltas);
        assert(queued.scrollingDeltaY==2 && queued.scrollingDeltaX==-1);
        // AppKit queueing can discard the binding; reapply it in the normal handler.
        if (window.windowNumber>0) {
            queued=bindNativeWheelToWindow(queued, window);
            assert(queued.window==window);
            assert(queued.scrollingDeltaY==2 && queued.scrollingDeltaX==-1);
        }
        CFRelease(copy); CFRelease(original);
    }
}
