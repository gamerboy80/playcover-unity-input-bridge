// Shared event handling; included after the host and backend callbacks.
#pragma once

static uint8_t nativeKeys[32];

static void setNativeKey(unsigned code, BOOL down) {
    if (code >= sizeof(nativeKeys) * 8) return;
    nativeKeys[code / 8] = (uint8_t)((nativeKeys[code / 8] & ~(1u << (code % 8))) | (down << (code % 8)));
}

static BOOL takeNativeKey(unsigned code) {
    if (code >= sizeof(nativeKeys) * 8) return NO;
    uint8_t mask = (uint8_t)(1u << (code % 8));
    if (!(nativeKeys[code / 8] & mask)) return NO;
    nativeKeys[code / 8] &= (uint8_t)~mask;
    return YES;
}

static void releaseInput(void) {
    BOOL hadKeys = NO;
    for (size_t i = 0; i < sizeof(keys); i++) {
        if (keys[i]) { hadKeys = YES; break; }
    }
    BOOL hadMouse = mouseState.buttons != 0 || mouseState.clicks != 0 ||
        mouseState.dx != 0 || mouseState.dy != 0 || mouseState.sx != 0 || mouseState.sy != 0;
    memset(keys, 0, sizeof(keys));
    mouseState.buttons = 0;
    mouseState.clicks = 0;
    mouseState.dx = mouseState.dy = mouseState.sx = mouseState.sy = 0;
    scrollRemainderX = scrollRemainderY = 0;
    if (hadKeys) sendKeyboard();
    if (hadMouse) sendMouse();
    forcedCapture = NO;
    setCapture(NO);
}

static id forwardNativeEvent(ZZZHostEvent *event, NSUInteger type) {
    releaseInput();
    if (type == 10) setNativeKey(event.keyCode, YES);
    else if (type == 11) setNativeKey(event.keyCode, NO);
    return event;
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
    BOOL motion=type==5 || type==6 || type==7 || type==27;
    id window=event.window;
    if (!window && (type==22 || (captured && motion))) {
        id app=[(id)NSClassFromString(@"NSApplication") sharedApplication];
        if ([app isActive]) window=[app keyWindow];
    }
    if (!window) return event;
    if (!routeGameEvent(window,gameWindow) || editingGameText()) {
        return forwardNativeEvent(event, type);
    }
    if (type==22) {
        if (event.hasPreciseScrollingDeltas) preciseEvents++; else wheelEvents++;
#if !GameLegacyBackend
        tracePending=YES;
#endif
        if (event.hasPreciseScrollingDeltas && !sawPreciseScroll) {
            sawPreciseScroll=YES; note("Precise trackpad scroll event received");
        }
    }
    if (type==22 && event.momentumPhase!=0) {
        scrollRemainderX=scrollRemainderY=0;
        return nil;
    }
    id wheelEvent=nil;
    if (type==10 || type==11 || type==12) {
        unsigned code=event.keyCode, key=unityKey(code);
        // Keep macOS Command shortcuts available; clear held game keys first.
        if (flags & (1u<<20)) return forwardNativeEvent(event, type);
        if (type==11 && takeNativeKey(code)) return event;
        if (type==10) setNativeKey(code, NO);
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
#if GameNativeMenuButtons
    // Let the native UI own the complete down/drag/up sequence in menus.
    if (!captured && (type==1 || type==2 || type==3 || type==4 ||
                      type==6 || type==7 || type==25 || type==26 || type==27)) return event;
#endif
    ZZZHostEvent *view=[window contentView];
    CGRect bounds=view.bounds;
    int width=((int (*)(void))(slide+GameScreenWidth))();
    int height=((int (*)(void))(slide+GameScreenHeight))();
    if (bounds.size.width<=0 || bounds.size.height<=0 || width<=0 || height<=0) return event;
    float scaleX=width/bounds.size.width, scaleY=height/bounds.size.height;
    // Precise gesture events can carry a stale location; use the actual window cursor.
    CGPoint point=type==22 ? [window mouseLocationOutsideOfEventStream] : event.locationInWindow;
    if ([view respondsToSelector:@selector(convertPoint:fromView:)]) {
        point=[view convertPoint:point fromView:nil];
    }
    mouseState.x=captured ? width*.5f : (float)((point.x-bounds.origin.x)*scaleX);
    mouseState.y=captured ? height*.5f : (float)((point.y-bounds.origin.y)*scaleY);
    if (motion) {
        // Focus/cursor repositioning can be included in the first relative delta.
        if (captured && !captureMotionReady(&discardFirstMotion,
                NSProcessInfo.processInfo.systemUptime,ignoreMotionUntil)) return nil;
        mouseState.dx=(float)event.deltaX*scaleX;
        mouseState.dy=-(float)event.deltaY*scaleY;
    } else if (type==22) {
        BOOL precise=event.hasPreciseScrollingDeltas;
        if (precise && (event.phase & (1u | 16u))) {
            scrollRemainderX=scrollRemainderY=0;
        }
        mouseState.sx=unityScroll(&scrollRemainderX, event.scrollingDeltaX, precise);
        mouseState.sy=unityScroll(&scrollRemainderY, event.scrollingDeltaY, precise);
        if (precise && (event.phase & (8u | 16u))) {
            scrollRemainderX=scrollRemainderY=0;
        }
        if (mouseState.sx==0 && mouseState.sy==0) return nil;
        if (precise) emittedSteps++;
        wheelEvent=nativeWheelEvent(event, window, mouseState.sx, mouseState.sy);
        if (precise && wheelEvent && ![wheelEvent hasPreciseScrollingDeltas]) {
            dispatch_async(dispatch_get_main_queue(), ^{
                id forwarded=handleEvent(wheelEvent);
                if (forwarded) dispatchNativeWheelToWindow(forwarded, window);
            });
            mouseState.sx=mouseState.sy=0;
            return nil;
        }
        if (!sawScroll && (mouseState.sx!=0 || mouseState.sy!=0)) {
            sawScroll=YES; note("Nonzero local scroll event received");
        }
        queuedScrolls++;
    } else {
        NSInteger button=event.buttonNumber;
        if (button>=0 && button<5) {
            BOOL down=(type==1 || type==3 || type==25);
            mouseState.buttons=(uint16_t)((mouseState.buttons&~(1u<<button)) | (down<<button));
            if (down) {
                NSInteger clicks=[event respondsToSelector:@selector(clickCount)] ? [event clickCount] : 1;
                mouseState.clicks=(uint16_t)(clicks>0 ? (clicks>UINT16_MAX ? UINT16_MAX : clicks) : 1);
            } else {
                mouseState.clicks=0;
            }
        }
    }
    sendMouse();
    if (type==22) return wheelEvent;
    return captured ? nil : event;
}

