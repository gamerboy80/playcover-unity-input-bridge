#import <AppKit/AppKit.h>
#include <assert.h>
#include "../src/InputState.h"
#include "../src/Scroll.h"
#include "../src/Capture.h"
#include "../src/EventRouting.h"

// Fake host and backend boundaries; EventHandler.h is the production handler.
@interface ZZZHostEvent : NSObject
@property NSUInteger type, modifierFlags, phase;
@property unsigned short keyCode;
@property BOOL isARepeat, hasPreciseScrollingDeltas;
@property NSInteger buttonNumber;
@property double deltaX, deltaY, scrollingDeltaX, scrollingDeltaY;
@property CGPoint locationInWindow, mouseLocationOutsideOfEventStream;
@property CGRect bounds;
@property id window, contentView, firstResponder;
@end
@implementation ZZZHostEvent
@end

static BOOL ready=YES, captured, forcedCapture, editing;
static bool discardFirstMotion;
static double ignoreMotionUntil, scrollRemainderX, scrollRemainderY;
static BOOL sawPreciseScroll, sawScroll;
static unsigned preciseEvents, wheelEvents, emittedSteps, queuedScrolls;
#if !GameLegacyBackend
static BOOL tracePending;
#endif
static uintptr_t slide;
static uint8_t keys[14];
static MouseState mouseState;
static id gameWindow;
static unsigned keyboardWrites, mouseWrites, nativeDispatches;
static float deliveredScroll;
static int screenWidth(void) { return 800; }
static int screenHeight(void) { return 600; }
#define GameScreenWidth ((uintptr_t)screenWidth)
#define GameScreenHeight ((uintptr_t)screenHeight)
static void note(const char *s) { (void)s; }
static BOOL editingGameText(void) { return editing; }
static unsigned unityKey(unsigned code) { return code==13 ? 37 : code==53 ? 60 : 0; }
static void setCapture(BOOL value) { captured=value; }
static void sendKeyboard(void) { keyboardWrites++; }
static void sendMouse(void) {
    mouseWrites++;
    deliveredScroll+=mouseState.sy;
    mouseState.dx=mouseState.dy=mouseState.sx=mouseState.sy=0;
}
static id nativeWheelEvent(ZZZHostEvent *event, id window, float x, float y) {
    if (!event.hasPreciseScrollingDeltas) return event;
    ZZZHostEvent *wheel=[ZZZHostEvent new];
    wheel.window=window; wheel.type=22;
    wheel.scrollingDeltaX=x/WheelUnitsPerStep;
    wheel.scrollingDeltaY=y/WheelUnitsPerStep;
    return wheel;
}
static void dispatchNativeWheelToWindow(id event, id window) {
    assert([event window]==window);
    assert(![event hasPreciseScrollingDeltas]);
    nativeDispatches++;
}
#include "../src/EventHandler.h"

int main(void) {
    @autoreleasepool {
        ZZZHostEvent *window=[ZZZHostEvent new], *view=[ZZZHostEvent new];
        view.bounds=CGRectMake(0,0,400,300);
        window.contentView=view;
        gameWindow=window;
        ZZZHostEvent *key=[ZZZHostEvent new];
        key.window=window; key.type=10; key.keyCode=13;
        ready=NO;
        assert(handleEvent(key)==key && keyboardWrites==0);
        ready=YES;
        assert(handleEvent(key)==nil && (keys[37/8]&(1u<<(37%8))));
        key.type=11;
        assert(handleEvent(key)==nil && keys[37/8]==0);
        key.type=10; handleEvent(key);
        editing=YES; captured=forcedCapture=YES; mouseState.buttons=1;
        assert(handleEvent(key)==key && keys[37/8]==0);
        assert(!captured && !forcedCapture && mouseState.buttons==0);
        editing=NO; handleEvent(key);
        window.firstResponder=[NSTextField new];
        assert(handleEvent(key)==key && keys[37/8]==0);
        window.firstResponder=nil; handleEvent(key);
        key.window=[ZZZHostEvent new];
        assert(handleEvent(key)==key && keys[37/8]==0);
        key.window=window; handleEvent(key);
        key.modifierFlags=1u<<20;
        assert(handleEvent(key)==key && keys[37/8]==0);
        key.modifierFlags=1u<<19; key.keyCode=46;
        assert(handleEvent(key)==nil && captured && forcedCapture);
        key.isARepeat=YES; handleEvent(key);
        assert(captured && forcedCapture);
        key.isARepeat=NO; key.modifierFlags=0; key.keyCode=53;
        handleEvent(key); assert(!captured && !forcedCapture);

        ZZZHostEvent *motion=[ZZZHostEvent new];
        motion.window=window; motion.type=5; motion.deltaX=20;
        captured=YES; discardFirstMotion=true;
        unsigned before=mouseWrites;
        assert(handleEvent(motion)==nil && mouseWrites==before);
        handleEvent(motion); assert(mouseWrites==before+1);
        releaseInput();

        ZZZHostEvent *scroll=[ZZZHostEvent new];
        scroll.window=window; scroll.type=22; scroll.hasPreciseScrollingDeltas=YES;
        scroll.scrollingDeltaY=8;
        before=mouseWrites;
        assert(handleEvent(scroll)==nil && mouseWrites==before);
        assert(handleEvent(scroll)==nil && mouseWrites==before);
        assert(emittedSteps==1 && queuedScrolls==0 && nativeDispatches==0);
        dispatch_async(dispatch_get_main_queue(), ^{
            assert(mouseWrites==before+1 && deliveredScroll==120);
            assert(queuedScrolls==1 && wheelEvents==1 && nativeDispatches==1);
            puts("Event handler checks passed");
            exit(0);
        });
    }
    dispatch_main();
}
