#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#include <mach-o/dyld.h>
#include <dlfcn.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include "Scroll.h"
#include "InputState.h"
#include "NativeWheel.h"
#include "MousePresence.h"
#include "Capture.h"
#include "EventRouting.h"
#include "Profile.h"

// Catalyst hosts AppKit. Resolve its classes at runtime, as PlayCover's plugin does.
@interface ZZZHostEvent : NSObject
+ (id)addLocalMonitorForEventsMatchingMask:(NSUInteger)mask handler:(id (^)(id))handler;
@property(readonly) NSUInteger type;
@property(readonly) unsigned short keyCode;
@property(readonly) NSUInteger modifierFlags;
@property(readonly) BOOL isARepeat;
@property(readonly) NSInteger buttonNumber;
@property(readonly) double deltaX;
@property(readonly) double deltaY;
@property(readonly) double scrollingDeltaX;
@property(readonly) double scrollingDeltaY;
@property(readonly) BOOL hasPreciseScrollingDeltas;
@property(readonly) NSUInteger phase;
@property(readonly) NSUInteger momentumPhase;
@property(readonly) void *CGEvent;
+ (id)eventWithCGEvent:(void *)event;
@property(readonly) CGPoint locationInWindow;
@property(readonly) CGPoint mouseLocationOutsideOfEventStream;
@property(readonly) NSInteger windowNumber;
@property BOOL acceptsMouseMovedEvents;
@property(readonly) id window;
@property(readonly) id contentView;
@property(readonly) CGRect bounds;
@property(readonly) CGRect frame;
+ (NSArray *)screens;
- (CGPoint)convertPoint:(CGPoint)point toView:(id)view;
- (CGPoint)convertPointToScreen:(CGPoint)point;
@property(readonly) id keyWindow;
@property(readonly) id mainWindow;
@property(readonly) BOOL isActive;
+ (id)sharedApplication;
+ (void)hide;
+ (void)unhide;
@end

static uintptr_t slide;
#if !GameLegacyBackend
static uintptr_t mouse, keyboard;
#endif
// The unity-input-system-v1 backend uses the 110-key, 14-byte Unity Key bitset.
static uint8_t keys[14];
static MouseState mouseState;
static id monitor;
static __weak id gameWindow;
static NSTimer *timer;
static FILE *output;
static BOOL ready, captured, forcedCapture;
static unsigned cursorHideClaims;
static int lastLock = -1, lastVisible = -1;
static int (*associateCursor)(int);
static int (*warpCursor)(CGPoint);
static unsigned int (*cursorVisible)(void);
static BOOL wasActive;
static bool discardFirstMotion;
static double captureNotBefore, ignoreMotionUntil;
static BOOL sawScroll, sawPreciseScroll;
#if !GameLegacyBackend
static BOOL sawScrollState;
#endif
#if !GameLegacyBackend
static size_t mouseStateBytes;
#endif
static double scrollRemainderX, scrollRemainderY;
static CreateWheel createCGWheel;
static void (*setCGInteger)(void *, uint32_t, int64_t);
static CGPoint (*getCGLocation)(void *);
static void (*setCGLocation)(void *, CGPoint);
static BOOL sawNativeWheel;
static unsigned preciseEvents, wheelEvents, emittedSteps, queuedScrolls;
#if !GameLegacyBackend
static unsigned controlSamples, processedSamples, traceLines;
static double lastTrace;
static BOOL tracePending;
#endif
static MousePresentCallback originalMousePresent;
static unsigned mousePresentCalls;

typedef struct {float x,y;} Vector2;

static void note(const char *message) {
    if (output) { fprintf(output, "%s\n", message); fflush(output); }
}

static bool bridgeMousePresent(void) {
    mousePresentCalls++;
    return ready || (originalMousePresent && originalMousePresent());
}

#if !GameLegacyBackend
#include "InputSystemStatics.h"
static void traceScroll(void) {
    if (!output || !tracePending || traceLines>=30) return;
    uintptr_t current=inputStatic(GameMouseType,GameFieldStaticMouse);
    BOOL enabled=NO;
    if (GameGetMouseProcessing!=0 && GameMouseProcessingEnabled!=0 && GameReadProcessedScroll!=0) {
        uintptr_t processing=((uintptr_t (*)(void))(slide+GameGetMouseProcessing))();
        if (processing) {
            enabled=((BOOL (*)(uintptr_t))(slide+GameMouseProcessingEnabled))(processing);
            Vector2 value=((Vector2 (*)(uintptr_t))(slide+GameReadProcessedScroll))(processing);
            if (value.x!=0 || value.y!=0) processedSamples++;
        }
    }
    uintptr_t scroll=*(uintptr_t *)(mouse+GameFieldMouseScroll);
    if (scroll && GameReadVector2!=0) {
        Vector2 value=((Vector2 (*)(uintptr_t,void *))(slide+GameReadVector2))(scroll,NULL);
        if (value.x!=0 || value.y!=0) controlSamples++;
    }
    double now=NSProcessInfo.processInfo.systemUptime;
    if (now-lastTrace<1) return;
    lastTrace=now; traceLines++; tracePending=NO;
    BOOL legacy=GameLegacyMousePresent!=0 ? ((BOOL (*)(void))(slide+GameLegacyMousePresent))() : NO;
    fprintf(output,"Scroll trace t=%.1f precise=%u coarse=%u steps=%u queued=%u controlSamples=%u processedSamples=%u enabled=%d currentID=%d bridgeID=%d legacyMousePresent=%d presentCalls=%u\n",
        now,preciseEvents,wheelEvents,emittedSteps,queuedScrolls,controlSamples,processedSamples,
        enabled,current ? *(int *)(current+GameFieldDeviceID) : -1,*(int *)(mouse+GameFieldDeviceID),
        legacy,mousePresentCalls);
    fflush(output);
}

#endif

static id nativeWheelEvent(ZZZHostEvent *event, id window, float x, float y) {
    if (!event.hasPreciseScrollingDeltas) return bindNativeWheelToWindow(event, window);
    if (!createCGWheel || !setCGInteger || !getCGLocation || !setCGLocation || !event.CGEvent) return event;
    void *copy=createNativeWheel(createCGWheel, x, y);
    if (!copy) return event;
    setCGLocation(copy, getCGLocation(event.CGEvent));
    if (window) {
        setCGInteger(copy, 91, [window windowNumber]);
        setCGInteger(copy, 92, [window windowNumber]);
    }
    id wheel=[(id)NSClassFromString(@"NSEvent") eventWithCGEvent:copy];
    CFRelease(copy);
    // CGEvent's window-under-pointer fields do not bind NSEvent.window.
    wheel=bindNativeWheelToWindow(wheel, window);
    if (wheel && !sawNativeWheel) { sawNativeWheel=YES; note("Trackpad threshold emitted a native wheel event"); }
    return wheel ?: event;
}

// macOS virtual keycodes -> the unity-input-system-v1 backend's Unity Key enum.
static unsigned unityKey(unsigned code) {
    static const uint8_t map[128] = {
        [0]=15,[1]=33,[2]=18,[3]=20,[4]=22,[5]=21,[6]=40,[7]=38,
        [8]=17,[9]=36,[11]=16,[12]=31,[13]=37,[14]=19,[15]=32,
        [16]=39,[17]=34,[18]=41,[19]=42,[20]=43,[21]=44,[22]=46,
        [23]=45,[24]=14,[25]=49,[26]=47,[27]=13,[28]=48,[29]=50,
        [30]=12,[31]=29,[32]=35,[33]=11,[34]=23,[35]=30,[36]=2,
        [37]=26,[38]=24,[39]=5,[40]=25,[41]=6,[42]=10,[43]=7,
        [44]=9,[45]=28,[46]=27,[47]=8,[48]=3,[49]=1,[50]=4,[51]=65,
        [53]=60,[55]=57,[54]=58,[56]=51,[60]=52,[58]=53,[61]=54,
        [59]=55,[62]=56,[57]=72,[65]=82,[67]=79,[69]=80,[71]=73,
        [75]=78,[76]=77,[78]=81,[81]=83,[82]=84,[83]=85,[84]=86,
        [85]=87,[86]=88,[87]=89,[88]=90,[89]=91,[91]=92,[92]=93,
        [122]=94,[120]=95,[99]=96,[118]=97,[96]=98,[97]=99,
        [98]=100,[100]=101,[101]=102,[109]=103,[103]=104,[111]=105,
        [115]=68,[119]=69,[116]=67,[121]=66,[117]=71,[114]=70,
        [123]=61,[124]=62,[125]=64,[126]=63
    };
    return code < sizeof(map) ? map[code] : 0;
}

#if GameLegacyBackend || GameLegacySupplement
#include "LegacyBackend.h"
#endif
#if GameLegacyBackend
static void sendKeyboard(void) { legacySendKeyboard(); }
static void sendMouse(void) { legacySendMouse(); }
#else
static void queueState(uintptr_t device, uint32_t format, const void *state, size_t size) {
    if (!ready || !device) return;
    int deviceID = *(int *)(device + GameFieldDeviceID);
    if (deviceID <= 0 || deviceID > UINT16_MAX || size > MaxDeviceStateBytes) return;
    uint8_t bytes[sizeof(StateHeader) + MaxDeviceStateBytes] = {0};
    StateHeader header = { .type=0x53544154, .size=(uint16_t)(sizeof(StateHeader)+size),
        .device=(uint16_t)deviceID, .time=((double (*)(void))(slide+GameNativeTime))(), .format=format };
    memcpy(bytes, &header, sizeof(header));
    memcpy(bytes+sizeof(header), state, size);
    ((void (*)(void *))(slide+GameQueueInputEvent))(bytes);
}

static void sendKeyboard(void) {
    queueState(keyboard, 0x4b455953, keys, sizeof(keys));
#if GameLegacySupplement
    legacySendKeyboard();
#endif
}
static void sendMouse(void) {
    if (GameCameraInput!=0 && captured && (mouseState.dx!=0 || mouseState.dy!=0) &&
        ((int (*)(void))(slide+GameCursorLock))()==1) {
        uintptr_t camera=inputStatic(GameCameraManagerType,GameCameraStaticOffset);
        int width=((int (*)(void))(slide+GameScreenWidth))();
        int height=((int (*)(void))(slide+GameScreenHeight))();
        if (camera && width>0 && height>0) {
            ((void (*)(uintptr_t,float,float,void *))(slide+GameCameraInput))(
                camera,mouseState.dx/width,mouseState.dy/height,NULL);
            static BOOL reported;
            if (!reported) { reported=YES; note("Captured motion delivered to the active camera input method"); }
        }
    }
    static BOOL sawMotion;
    if (!sawMotion && (mouseState.dx!=0 || mouseState.dy!=0)) {
        sawMotion=YES; note("Native mouse motion forwarded to Unity");
    }
#if GameLegacySupplement
    MouseState saved=mouseState;
    legacySendMouse();
    mouseState=saved;
#endif
    // FastMouse appends pressure/radius controls beyond the standard 30-byte state.
    uint8_t state[MaxDeviceStateBytes];
    size_t size=packMouseState(state, &mouseState, mouseStateBytes);
    if (size) {
        ((void (*)(uintptr_t))(slide+GameMouseMakeCurrent))(mouse);
        queueState(mouse, 0x4d4f5553, state, size);
    }
    mouseState.dx = mouseState.dy = mouseState.sx = mouseState.sy = 0;
}

#endif

static void hideHostCursor(void) { [(id)NSClassFromString(@"NSCursor") hide]; }
static void unhideHostCursor(void) { [(id)NSClassFromString(@"NSCursor") unhide]; }

static void setCapture(BOOL value) {
    if (captured == value) {
        // AppKit/Unity can restore visibility after Dock activation finishes.
        if (captured && cursorVisible && cursorVisible())
            balanceCursorHide(&cursorHideClaims,true,true,hideHostCursor,unhideHostCursor);
        return;
    }
    if (value) {
        id app=[(id)NSClassFromString(@"NSApplication") sharedApplication];
        ZZZHostEvent *window=gameWindow;
        if ([app keyWindow]!=window) return;
        ZZZHostEvent *view=window.contentView;
        CGRect bounds=view.bounds;
        CGPoint cursor=[view convertPoint:window.mouseLocationOutsideOfEventStream fromView:nil];
        if (!window || !view || bounds.size.width<=0 || bounds.size.height<=0) return;
        window.acceptsMouseMovedEvents=YES;
        if (!cursorInsideContent(cursor,bounds)) {
            NSArray *screens=[(id)NSClassFromString(@"NSScreen") screens];
            ZZZHostEvent *primary=(id)screens.firstObject;
            CGPoint center=CGPointMake(CGRectGetMidX(bounds),CGRectGetMidY(bounds));
            CGPoint screen=[window convertPointToScreen:[view convertPoint:center toView:nil]];
            if (!primary || !warpCursor || warpCursor(captureScreenPoint(screen,CGRectGetMaxY(primary.frame)))!=0) {
                if (associateCursor) associateCursor(1);
                return;
            }
            note("Moved outside pointer into the game before capture");
        }
    }
    if (value && (!associateCursor || associateCursor(0) != 0)) {
        note("Pointer capture unavailable");
        return;
    }
    if (!value && associateCursor) associateCursor(1);
    captured = value;
#if GameNativeMenuButtons
    if (!captured && mouseState.buttons) {
        mouseState.buttons=0;
        mouseState.clicks=0;
        sendMouse();
    }
#endif
    if (value) {
        ignoreMotionUntil=NSProcessInfo.processInfo.systemUptime+.1;
        discardFirstMotion=YES;
    }
    balanceCursorHide(&cursorHideClaims,value,cursorVisible && cursorVisible(),hideHostCursor,unhideHostCursor);
    note(value ? "Pointer captured" : "Pointer released");
}

static BOOL editingUIKitText(UIView *view) {
    if (view.isFirstResponder &&
        ([view isKindOfClass:UITextField.class] || [view isKindOfClass:UITextView.class])) return YES;
    for (UIView *child in view.subviews) if (editingUIKitText(child)) return YES;
    return NO;
}

static BOOL editingGameText(void) {
    for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
        if (![scene isKindOfClass:UIWindowScene.class]) continue;
        for (UIWindow *window in ((UIWindowScene *)scene).windows)
            if (window.isKeyWindow && editingUIKitText(window)) return YES;
    }
    return NO;
}

#include "EventHandler.h"

#if GameLegacyBackend || GameLegacySupplement
static void traceLegacy(void) {
    static double previous;
    static unsigned lines;
    double now=NSProcessInfo.processInfo.systemUptime;
    if (!output || lines>=60 || now-previous<5) return;
    previous=now; lines++;
    unsigned intact=0;
    const uintptr_t offsets[]={GameMousePositionSlot,GameMouseScrollSlot,GameMouseButtonSlot,
        GameMouseButtonDownSlot,GameMouseButtonUpSlot,GameAxisSlot,GameAxisRawSlot,
        GameKeySlot,GameKeyDownSlot,GameKeyUpSlot,GameAnyKeySlot,GameAnyKeyDownSlot};
    void *callbacks[]={(void *)legacyPosition,(void *)legacyScroll,(void *)legacyHeld,
        (void *)legacyDown,(void *)legacyUp,(void *)legacyAxisSmooth,(void *)legacyAxisRaw,
        (void *)legacyKeyHeld,(void *)legacyKeyDown,(void *)legacyKeyUp,(void *)legacyAnyHeld,(void *)legacyAnyDown};
    for (unsigned i=0;i<12;i++) intact+=*(void **)(slide+offsets[i])==callbacks[i];
    fprintf(output,"Legacy input: keyWrites=%u keyReads=%u mouseReads=%u scrollReads=%u axisReads=%u presenceReads=%u hooks=%u/12 wheel=%u queued=%u frame=%d positiveKeys=%u positiveScrolls=%u namedAxes=%u nonzeroAxes=%u\n",
        legacyKeyWrites,legacyKeyReads,legacyMouseReads,legacyScrollReads,legacyAxisReads,
        mousePresentCalls,intact,wheelEvents,queuedScrolls,legacyFrame,
        legacyPositiveKeys,legacyPositiveScrolls,legacyNamedAxes,legacyNonzeroAxes);
    fflush(output);
}
#endif

static void initializeDevices(void) {
    id hostApp=[(id)NSClassFromString(@"NSApplication") sharedApplication];
    if (!gameWindow) gameWindow=[hostApp mainWindow];
    if (!slide) {
        for (uint32_t i=0;i<_dyld_image_count();i++) {
            const char *name=_dyld_get_image_name(i);
            if (name && [[NSString stringWithUTF8String:name] hasSuffix:@GameImageSuffix]) {
                slide=(uintptr_t)_dyld_get_image_vmaddr_slide(i); break;
            }
        }
    }
    if (!slide) return;
    if (!ready) {
#if GameLegacyBackend
        if (!initializeLegacy()) return;
        Class eventClass=NSClassFromString(@"NSEvent");
#else
        if (!inputStatic(GameInputSystemType,GameFieldStaticInputManager) ||
            !inputStatic(GameKeyboardType,GameFieldStaticKeyboard)) return;
#if GameLegacySupplement
        static BOOL legacyReady;
        if (!legacyReady) {
            if (!initializeLegacy()) return;
            legacyReady=YES;
        }
#endif
        Class eventClass=NSClassFromString(@"NSEvent");
        if (!eventClass) { note("AppKit event class unavailable"); [timer invalidate]; return; }
        void *(*newString)(const char *,int)=(void *)(slide+GameNewString);
        uintptr_t (*addDevice)(void *,void *,void *)=(void *)(slide+GameAddDevice);
        mouse=addDevice(newString("Mouse",5),newString("Desktop Mouse",13),NULL);
        keyboard=addDevice(newString("Keyboard",8),newString("Desktop Keyboard",16),NULL);
        if (!mouse || !keyboard || !*(uintptr_t *)(mouse+GameFieldMousePosition) || !*(uintptr_t *)(mouse+GameFieldMouseDelta)) {
            note("Device creation failed validation; bridge disabled"); [timer invalidate]; return;
        }
        uint32_t *mouseBlock=(uint32_t *)(mouse+GameFieldStateBlock);
        mouseStateBytes=(mouseBlock[3]+7u)/8u;
        if (mouseBlock[0]!=0x4d4f5553 || mouseStateBytes!=GameMouseStateBytes) {
            if (output) { fprintf(output,"Mouse layout: format=%08x bytes=%zu expected=%u\n",mouseBlock[0],mouseStateBytes,GameMouseStateBytes); fflush(output); }
            note("Unexpected Mouse state layout; bridge disabled"); [timer invalidate]; return;
        }
#endif
        ready=YES;
        if (GameLegacyMousePresentSlot!=0) {
            MousePresentCallback *slot=(void *)(slide+GameLegacyMousePresentSlot);
            if (installMousePresence(slot, bridgeMousePresent, &originalMousePresent)) {
                note("Legacy mouse presence bridged to the validated Unity Mouse");
            }
        }
        NSUInteger mask=0;
        const unsigned types[]={1,2,3,4,5,6,7,10,11,12,22,25,26,27};
        for (unsigned i=0;i<sizeof(types)/sizeof(types[0]);i++) mask|=(NSUInteger)1<<types[i];
        monitor=[(id)eventClass addLocalMonitorForEventsMatchingMask:mask handler:^id(id e) { return handleEvent(e); }];
        if (!monitor) { ready=NO; note("Event monitor unavailable"); [timer invalidate]; return; }
#if !GameLegacyBackend
        uintptr_t scroll=*(uintptr_t *)(mouse+GameFieldMouseScroll);
        if (output && scroll) {
            uint32_t *block=(uint32_t *)(scroll+GameFieldStateBlock);
            fprintf(output,"Scroll control format=%08x byteOffset=%u bitOffset=%u size=%u\n",block[0],block[1],block[2],block[3]);
            fflush(output);
        }
#endif
        [[NSNotificationCenter defaultCenter] addObserverForName:@"NSApplicationDidResignActiveNotification" object:nil queue:nil usingBlock:^(NSNotification *n) { (void)n; releaseInput(); }];
        [[NSNotificationCenter defaultCenter] addObserverForName:@"NSApplicationWillTerminateNotification" object:nil queue:nil usingBlock:^(NSNotification *n) { (void)n; releaseInput(); }];
#if !GameLegacyBackend
        ((void (*)(uintptr_t))(slide+GameMouseMakeCurrent))(mouse);
        if (GameEnableMouseProcessing) {
            ((void (*)(BOOL))(slide+GameEnableMouseProcessing))(YES);
            note("Game mouse processing initialized before login");
        }
#endif
        note("Native devices initialized; local keyboard/mouse events enabled. Option+M toggles capture; Escape releases manual capture.");
#if !GameLegacyBackend
        if (output) { fprintf(output,"mouseID=%d keyboardID=%d position=%p delta=%p\n",*(int *)(mouse+GameFieldDeviceID),*(int *)(keyboard+GameFieldDeviceID),(void *)*(uintptr_t *)(mouse+GameFieldMousePosition),(void *)*(uintptr_t *)(mouse+GameFieldMouseDelta)); fflush(output); }
#endif
    }
#if !GameLegacyBackend
    if (sawScroll && !sawScrollState && GameReadVector2!=0) {
        uintptr_t scroll=*(uintptr_t *)(mouse+GameFieldMouseScroll);
        if (scroll) {
            Vector2 value=((Vector2 (*)(uintptr_t,void *))(slide+GameReadVector2))(scroll,NULL);
            if (value.x!=0 || value.y!=0) { sawScrollState=YES; note("Unity scroll control received nonzero state"); }
        }
    }
    traceScroll();
    uintptr_t currentMouse=inputStatic(GameMouseType,GameFieldStaticMouse);
    if (!currentMouse || !*(uintptr_t *)(currentMouse+GameFieldMousePosition) || !*(uintptr_t *)(currentMouse+GameFieldMouseDelta)) {
        ((void (*)(uintptr_t))(slide+GameMouseMakeCurrent))(mouse);
    }
#endif
#if GameLegacyBackend || GameLegacySupplement
    traceLegacy();
#endif
    id app=[(id)NSClassFromString(@"NSApplication") sharedApplication];
    BOOL active=[app isActive] && [app keyWindow]==gameWindow &&
        routeGameEvent(gameWindow,gameWindow) && !editingGameText();
    if (!active && wasActive) releaseInput();
    double now=NSProcessInfo.processInfo.systemUptime;
    if (active && !wasActive) {
        captureNotBefore=now+.15;
        setCapture(NO);
    }
    wasActive=active;
    if (active && now<captureNotBefore) {
        // Let Dock activation and the game's native focus handler finish first.
        if (associateCursor) associateCursor(1);
        return;
    }
    int lock=((int (*)(void))(slide+GameCursorLock))();
    int visible=((BOOL (*)(void))(slide+GameCursorVisible))();
    if (lock!=lastLock || visible!=lastVisible) {
        if (output) { fprintf(output,"Unity cursor lock=%d visible=%d\n",lock,visible); fflush(output); }
        lastLock=lock; lastVisible=visible;
    }
    setCapture(active && (forcedCapture || lock==1));
}

__attribute__((constructor)) static void start(void) {
    assert(unityKey(13)==37 && unityKey(0)==15 && unityKey(122)==94 && unityKey(111)==105);
    assert(unityKey(128)==0 && unityKey(10)==0);
    dispatch_async(dispatch_get_main_queue(), ^{
        NSBundle *bundle=[NSBundle mainBundle];
        if (![bundle.bundleIdentifier isEqualToString:@GameBundleID] ||
            ![[bundle objectForInfoDictionaryKey:@"CFBundleShortVersionString"] isEqualToString:@GameVersion]) {
            NSLog(@"NativeInputBridge: profile %@ does not match this app; disabled", @GameProfileID);
            return;
        }
        NSString *path=[NSHomeDirectory() stringByAppendingPathComponent:@"Documents/LogDir/NativeInputBridge.log"];
        [[NSFileManager defaultManager] createDirectoryAtPath:path.stringByDeletingLastPathComponent
            withIntermediateDirectories:YES attributes:nil error:nil];
        output=fopen(path.fileSystemRepresentation,"w");
        note(GameProfileID " native input experiment; no key logging");
        associateCursor=(int (*)(int))dlsym(RTLD_DEFAULT,"CGAssociateMouseAndMouseCursorPosition");
        warpCursor=(int (*)(CGPoint))dlsym(RTLD_DEFAULT,"CGWarpMouseCursorPosition");
        cursorVisible=(unsigned int (*)(void))dlsym(RTLD_DEFAULT,"CGCursorIsVisible");
        createCGWheel=(CreateWheel)dlsym(RTLD_DEFAULT,"CGEventCreateScrollWheelEvent");
        setCGInteger=(void (*)(void *,uint32_t,int64_t))dlsym(RTLD_DEFAULT,"CGEventSetIntegerValueField");
        getCGLocation=(CGPoint (*)(void *))dlsym(RTLD_DEFAULT,"CGEventGetLocation");
        setCGLocation=(void (*)(void *,CGPoint))dlsym(RTLD_DEFAULT,"CGEventSetLocation");
        timer=[NSTimer scheduledTimerWithTimeInterval:1.0/60.0 repeats:YES block:^(NSTimer *t) { (void)t; initializeDevices(); }];
    });
}
