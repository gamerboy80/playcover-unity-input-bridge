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
@property(readonly) void *CGEvent;
+ (id)eventWithCGEvent:(void *)event;
@property(readonly) CGPoint locationInWindow;
@property(readonly) CGPoint mouseLocationOutsideOfEventStream;
@property(readonly) id window;
@property(readonly) id contentView;
@property(readonly) CGRect bounds;
@property(readonly) id keyWindow;
@property(readonly) BOOL isActive;
+ (id)sharedApplication;
+ (void)hide;
+ (void)unhide;
@end

static uintptr_t slide, mouse, keyboard;
static uint8_t keys[14];
static MouseState mouseState;
static id monitor;
static NSTimer *timer;
static FILE *output;
static BOOL ready, captured, forcedCapture;
static int lastLock = -1, lastVisible = -1;
static int (*associateCursor)(int);
static BOOL sawScroll, sawScrollState, sawPreciseScroll;
static size_t mouseStateBytes;
static double scrollRemainderX, scrollRemainderY;
static void *(*copyCGEvent)(void *);
static void (*setCGInteger)(void *, uint32_t, int64_t);
static BOOL sawNativeWheel;

static void note(const char *message) {
    if (output) { fprintf(output, "%s\n", message); fflush(output); }
}

static id nativeWheelEvent(ZZZHostEvent *event, float x, float y) {
    if (!event.hasPreciseScrollingDeltas) return event;
    if (!copyCGEvent || !setCGInteger || !event.CGEvent) return event;
    void *copy=copyCGEvent(event.CGEvent);
    if (!copy) return event;
    setNativeWheelFields(copy, setCGInteger, x, y);
    id wheel=[(id)NSClassFromString(@"NSEvent") eventWithCGEvent:copy];
    CFRelease(copy);
    if (wheel && !sawNativeWheel) { sawNativeWheel=YES; note("Trackpad threshold emitted a native wheel event"); }
    return wheel ?: event;
}

// macOS virtual keycodes -> this build's verified Unity Key enum.
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

static void queueState(uintptr_t device, uint32_t format, const void *state, size_t size) {
    if (!ready || !device) return;
    int deviceID = *(int *)(device + 0x144);
    if (deviceID <= 0 || deviceID > UINT16_MAX || size > MaxDeviceStateBytes) return;
    uint8_t bytes[sizeof(StateHeader) + MaxDeviceStateBytes] = {0};
    StateHeader header = { .type=0x53544154, .size=(uint16_t)(sizeof(StateHeader)+size),
        .device=(uint16_t)deviceID, .time=((double (*)(void))(slide+0x138d66b4))(), .format=format };
    memcpy(bytes, &header, sizeof(header));
    memcpy(bytes+sizeof(header), state, size);
    ((void (*)(void *))(slide+0x138d66f0))(bytes);
}

static void sendKeyboard(void) { queueState(keyboard, 0x4b455953, keys, sizeof(keys)); }
static void sendMouse(void) {
    // FastMouse appends pressure/radius controls beyond the standard 30-byte state.
    uint8_t state[MaxDeviceStateBytes];
    size_t size=packMouseState(state, &mouseState, mouseStateBytes);
    if (size) {
        ((void (*)(uintptr_t))(slide+0x133ade68))(mouse);
        queueState(mouse, 0x4d4f5553, state, size);
    }
    mouseState.dx = mouseState.dy = mouseState.sx = mouseState.sy = 0;
}

static void setCapture(BOOL value) {
    if (captured == value) return;
    if (value && (!associateCursor || associateCursor(0) != 0)) {
        note("Pointer capture unavailable");
        return;
    }
    if (!value && associateCursor) associateCursor(1);
    captured = value;
    Class cursorClass = NSClassFromString(@"NSCursor");
    if (value) [(id)cursorClass hide]; else [(id)cursorClass unhide];
    note(value ? "Pointer captured" : "Pointer released");
}

static void releaseInput(void) {
    memset(keys, 0, sizeof(keys));
    mouseState.buttons = 0;
    scrollRemainderX = scrollRemainderY = 0;
    sendKeyboard(); sendMouse();
    forcedCapture = NO;
    setCapture(NO);
}

static void updateModifiers(NSUInteger flags) {
    const unsigned values[] = {51,52,55,56,53,54,57,58,72};
    const BOOL states[] = {(flags&2)!=0,(flags&4)!=0,(flags&1)!=0,(flags&0x2000)!=0,
        (flags&0x20)!=0,(flags&0x40)!=0,(flags&8)!=0,(flags&0x10)!=0,(flags&0x10000)!=0};
    for (unsigned i=0;i<sizeof(values)/sizeof(values[0]);i++) {
        unsigned k=values[i];
        keys[k/8] = (uint8_t)((keys[k/8]&~(1u<<(k%8))) | (states[i]<<(k%8)));
    }
}

static id handleEvent(ZZZHostEvent *event) {
    if (!ready) return event;
    NSUInteger type=event.type, flags=event.modifierFlags;
    id window=event.window;
    if (type==22) {
        if (event.hasPreciseScrollingDeltas && !sawPreciseScroll) {
            sawPreciseScroll=YES; note("Precise trackpad scroll event received");
        }
        if (!window) {
            id app=[(id)NSClassFromString(@"NSApplication") sharedApplication];
            if ([app isActive]) window=[app keyWindow];
        }
    }
    if (!window) return event;
    id wheelEvent=nil;
    if (type==10 || type==11 || type==12) {
        unsigned code=event.keyCode, key=unityKey(code);
        // Keep macOS Command shortcuts available; clear held game keys first.
        if (flags & (1u<<20)) { releaseInput(); return event; }
        if (type==10 && code==46 && (flags&(1u<<19))) {
            if (!event.isARepeat) { forcedCapture=!forcedCapture; setCapture(forcedCapture); }
            return nil;
        }
        if (type==10 && code==53 && forcedCapture) { forcedCapture=NO; setCapture(NO); }
        updateModifiers(flags);
        if (type!=12 && key) {
            keys[key/8] = (uint8_t)((keys[key/8]&~(1u<<(key%8))) | ((type==10)<<(key%8)));
        }
        sendKeyboard();
        return key ? nil : event;
    }
    ZZZHostEvent *view=[window contentView];
    CGRect bounds=view.bounds;
    int width=((int (*)(void))(slide+0x1389069c))();
    int height=((int (*)(void))(slide+0x138906ac))();
    if (bounds.size.width<=0 || bounds.size.height<=0 || width<=0 || height<=0) return event;
    float scaleX=width/bounds.size.width, scaleY=height/bounds.size.height;
    // Precise gesture events can carry a stale location; use the actual window cursor.
    CGPoint point=type==22 ? [window mouseLocationOutsideOfEventStream] : event.locationInWindow;
    mouseState.x=captured ? width*.5f : point.x*scaleX;
    mouseState.y=captured ? height*.5f : point.y*scaleY;
    if (type==5 || type==6 || type==7 || type==27) {
        mouseState.dx=(float)event.deltaX*scaleX;
        mouseState.dy=-(float)event.deltaY*scaleY;
    } else if (type==22) {
        BOOL precise=event.hasPreciseScrollingDeltas;
        if (precise && (event.phase & (1u | 16u))) {
            scrollRemainderX=scrollRemainderY=0;
        }
        mouseState.sx=unityScroll(&scrollRemainderX, event.scrollingDeltaX, precise);
        mouseState.sy=unityScroll(&scrollRemainderY, event.scrollingDeltaY, precise);
        if (mouseState.sx==0 && mouseState.sy==0) return nil;
        wheelEvent=nativeWheelEvent(event, mouseState.sx, mouseState.sy);
        if (!sawScroll && (mouseState.sx!=0 || mouseState.sy!=0)) {
            sawScroll=YES; note("Nonzero local scroll event received");
        }
    } else {
        NSInteger button=event.buttonNumber;
        if (button>=0 && button<5) {
            BOOL down=(type==1 || type==3 || type==25);
            mouseState.buttons=(uint16_t)((mouseState.buttons&~(1u<<button)) | (down<<button));
            mouseState.clicks=down ? 1 : 0;
        }
    }
    sendMouse();
    if (type==22) return wheelEvent;
    return captured ? nil : event;
}

static void initializeDevices(void) {
    if (!slide) {
        for (uint32_t i=0;i<_dyld_image_count();i++) {
            const char *name=_dyld_get_image_name(i);
            if (name && strstr(name,"/UnityFramework.framework/UnityFramework")) {
                slide=(uintptr_t)_dyld_get_image_vmaddr_slide(i); break;
            }
        }
    }
    if (!slide) return;
    uintptr_t statics=*(uintptr_t *)(slide+0x1c69e278);
    if (!statics || !*(uintptr_t *)(statics+0x2ae78) || !*(uintptr_t *)(statics+0x2b2c0)) return;
    if (!ready) {
        Class eventClass=NSClassFromString(@"NSEvent");
        if (!eventClass) { note("AppKit event class unavailable"); [timer invalidate]; return; }
        void *(*newString)(const char *,int)=(void *)(slide+0x13a84cb0);
        uintptr_t (*addDevice)(void *,void *,void *)=(void *)(slide+0x133fa120);
        mouse=addDevice(newString("Mouse",5),newString("Desktop Mouse",13),NULL);
        keyboard=addDevice(newString("Keyboard",8),newString("Desktop Keyboard",16),NULL);
        if (!mouse || !keyboard || !*(uintptr_t *)(mouse+0x178) || !*(uintptr_t *)(mouse+0x170)) {
            note("Device creation failed validation; bridge disabled"); [timer invalidate]; return;
        }
        uint32_t *mouseBlock=(uint32_t *)(mouse+0x98);
        mouseStateBytes=(mouseBlock[3]+7u)/8u;
        if (mouseBlock[0]!=0x4d4f5553 || mouseStateBytes<sizeof(MouseState) || mouseStateBytes>MaxDeviceStateBytes) {
            note("Unexpected Mouse state layout; bridge disabled"); [timer invalidate]; return;
        }
        ready=YES;
        NSUInteger mask=0;
        const unsigned types[]={1,2,3,4,5,6,7,10,11,12,22,25,26,27};
        for (unsigned i=0;i<sizeof(types)/sizeof(types[0]);i++) mask|=(NSUInteger)1<<types[i];
        monitor=[(id)eventClass addLocalMonitorForEventsMatchingMask:mask handler:^id(id e) { return handleEvent(e); }];
        if (!monitor) { ready=NO; note("Event monitor unavailable"); [timer invalidate]; return; }
        uintptr_t scroll=*(uintptr_t *)(mouse+0x188);
        if (output && scroll) {
            uint32_t *block=(uint32_t *)(scroll+0x98);
            fprintf(output,"Scroll control format=%08x byteOffset=%u bitOffset=%u size=%u\n",block[0],block[1],block[2],block[3]);
            fflush(output);
        }
        [[NSNotificationCenter defaultCenter] addObserverForName:@"NSApplicationDidResignActiveNotification" object:nil queue:nil usingBlock:^(NSNotification *n) { (void)n; releaseInput(); }];
        [[NSNotificationCenter defaultCenter] addObserverForName:@"NSApplicationWillTerminateNotification" object:nil queue:nil usingBlock:^(NSNotification *n) { (void)n; releaseInput(); }];
        ((void (*)(uintptr_t))(slide+0x133ade68))(mouse);
        ((void (*)(BOOL))(slide+0xb0a61d4))(YES);
        note("Game mouse processing initialized before login");
        note("Native devices initialized; local keyboard/mouse events enabled. Option+M toggles capture; Escape releases manual capture.");
        if (output) { fprintf(output,"mouseID=%d keyboardID=%d position=%p delta=%p\n",*(int *)(mouse+0x144),*(int *)(keyboard+0x144),(void *)*(uintptr_t *)(mouse+0x178),(void *)*(uintptr_t *)(mouse+0x170)); fflush(output); }
    }
    if (sawScroll && !sawScrollState) {
        uintptr_t scroll=*(uintptr_t *)(mouse+0x188);
        if (scroll) {
            typedef struct {float x,y;} Vector2;
            Vector2 value=((Vector2 (*)(uintptr_t,void *))(slide+0x9b2cd20))(scroll,NULL);
            if (value.x!=0 || value.y!=0) { sawScrollState=YES; note("Unity scroll control received nonzero state"); }
        }
    }
    uintptr_t currentMouse=*(uintptr_t *)(statics+0x2b4c0);
    if (!currentMouse || !*(uintptr_t *)(currentMouse+0x178) || !*(uintptr_t *)(currentMouse+0x170)) {
        ((void (*)(uintptr_t))(slide+0x133ade68))(mouse);
    }
    id app=[(id)NSClassFromString(@"NSApplication") sharedApplication];
    BOOL active=[app isActive];
    int lock=((int (*)(void))(slide+0x1380e1c8))();
    int visible=((BOOL (*)(void))(slide+0x1380e1a8))();
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
        NSString *path=[NSHomeDirectory() stringByAppendingPathComponent:@"Documents/LogDir/NativeInputBridge.log"];
        output=fopen(path.fileSystemRepresentation,"w");
        note("ZZZ 3.3.0 native input experiment; no key logging");
        associateCursor=(int (*)(int))dlsym(RTLD_DEFAULT,"CGAssociateMouseAndMouseCursorPosition");
        copyCGEvent=(void *(*)(void *))dlsym(RTLD_DEFAULT,"CGEventCreateCopy");
        setCGInteger=(void (*)(void *,uint32_t,int64_t))dlsym(RTLD_DEFAULT,"CGEventSetIntegerValueField");
        timer=[NSTimer scheduledTimerWithTimeInterval:1.0/60.0 repeats:YES block:^(NSTimer *t) { (void)t; initializeDevices(); }];
    });
}
