// Shared event handling; included after the host and backend callbacks.
#pragma once

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
        if (event.hasPreciseScrollingDeltas) preciseEvents++; else wheelEvents++;
#if !GameLegacyBackend
        tracePending=YES;
#endif
        if (event.hasPreciseScrollingDeltas && !sawPreciseScroll) {
            sawPreciseScroll=YES; note("Precise trackpad scroll event received");
        }
        if (!window) {
            id app=[(id)NSClassFromString(@"NSApplication") sharedApplication];
            if ([app isActive]) window=[app keyWindow];
        }
    }
    if (!window) return event;
    if (!routeGameEvent(window,gameWindow)) { releaseInput(); return event; }
    id wheelEvent=nil;
    if (type==10 || type==11 || type==12) {
        if (editingGameText()) { releaseInput(); return event; }
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
    int width=((int (*)(void))(slide+GameScreenWidth))();
    int height=((int (*)(void))(slide+GameScreenHeight))();
    if (bounds.size.width<=0 || bounds.size.height<=0 || width<=0 || height<=0) return event;
    float scaleX=width/bounds.size.width, scaleY=height/bounds.size.height;
    // Precise gesture events can carry a stale location; use the actual window cursor.
    CGPoint point=type==22 ? [window mouseLocationOutsideOfEventStream] : event.locationInWindow;
    mouseState.x=captured ? width*.5f : point.x*scaleX;
    mouseState.y=captured ? height*.5f : point.y*scaleY;
    if (type==5 || type==6 || type==7 || type==27) {
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
            mouseState.clicks=down ? 1 : 0;
        }
    }
    sendMouse();
    if (type==22) return wheelEvent;
    return captured ? nil : event;
}

