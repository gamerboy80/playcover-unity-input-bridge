#import <Foundation/Foundation.h>
#include <assert.h>
#include <stdio.h>
static FILE *output;
#include "../src/InputState.h"
#include "../src/Scroll.h"
static uintptr_t slide;
static uint8_t keys[14];
static MouseState mouseState;
static int frame;
static void *slots[12];
static int frameCount(void) { return frame; }
static BOOL nativeKey(int code) { return code==511; }
static BOOL anyKey(void) { return NO; }
static BOOL button(int b) { return b==4; }
static float axis(void *s) { (void)s; return 7; }
static void position(float *p) { p[0]=5;p[1]=6;p[2]=0; }
#define GameScrollWrapperReturn 0x2000
#define GameUIScrollReturn 0x1000
#define GameLegacyScrollUnitsPerStep 120
#define GameFrameCount ((uintptr_t)frameCount)
#define GameKeySlot ((uintptr_t)&slots[7])
#define GameKeyDownSlot ((uintptr_t)&slots[8])
#define GameKeyUpSlot ((uintptr_t)&slots[9])
#define GameAnyKeySlot ((uintptr_t)&slots[10])
#define GameAnyKeyDownSlot ((uintptr_t)&slots[11])
#define GameMousePositionSlot ((uintptr_t)&slots[0])
#define GameMouseScrollSlot ((uintptr_t)&slots[1])
#define GameMouseButtonSlot ((uintptr_t)&slots[2])
#define GameMouseButtonDownSlot ((uintptr_t)&slots[3])
#define GameMouseButtonUpSlot ((uintptr_t)&slots[4])
#define GameAxisSlot ((uintptr_t)&slots[5])
#define GameAxisRawSlot ((uintptr_t)&slots[6])
#include "../src/LegacyBackend.h"
int main(void) {
    assert(!initializeLegacy());
    slots[0]=slots[1]=(void *)position;
    slots[2]=slots[3]=slots[4]=(void *)button;
    slots[5]=slots[6]=(void *)axis;
    slots[7]=slots[8]=slots[9]=(void *)nativeKey;
    slots[10]=slots[11]=(void *)anyKey;
    assert(initializeLegacy());
    assert(legacyKey(37)=='w' && legacyKey(94)==282 && legacyKey(105)==293);
    keys[37/8]|=1u<<(37%8); sendKeyboard();
    assert(legacyKeyHeld('w') && legacyKeyDown('w') && legacyAnyHeld() && legacyAnyDown());
    memset(keys,0,sizeof(keys));sendKeyboard();frame++;
    assert(!legacyKeyHeld('w') && legacyKeyUp('w') && !legacyKeyDown('w') && !legacyAnyHeld());
    assert(legacyKeyHeld(511) && !legacyKeyHeld(512));
    frame++; assert(!legacyKeyUp('w'));
    assert(legacyKeyReads>0 && legacyKeyWrites==2);
    mouseState=(MouseState){.x=100,.y=200,.buttons=1,.sx=120,.sy=-240};sendMouse();
    frame++;
    float p[3];legacyPosition(p);assert(p[0]==100 && p[1]==200);
    assert(legacyDown(0) && legacyDown(0) && legacyHeld(0));
    float scroll[2];legacyScroll(scroll);assert(scroll[0]==120 && scroll[1]==-240);
    legacyScrollForCaller(scroll,GameUIScrollReturn);
    assert(scroll[0]==1 && scroll[1]==-2);
    legacyScrollForCaller(scroll,GameUIScrollReturn+4);
    assert(scroll[0]==120 && scroll[1]==-240);
    legacyScroll(scroll);assert(scroll[1]==-240); // Polling twice must not consume the frame.
    frame++;legacyScroll(scroll);assert(scroll[1]==0 && !legacyDown(0));
    mouseState.buttons=0;sendMouse();frame++;assert(legacyUp(0) && !legacyHeld(0));
    frame++;assert(!legacyUp(0));
    assert(legacyHeld(4)); // Preserve unrelated native mouse input.
    assert(legacyAxisRaw(NULL)==7);
    struct { uint64_t header[2]; int length; uint16_t text[8]; } name={.length=7,
        .text={'m','o','u','s','e',' ','x'}};
    mouseState.dx=20;sendMouse();frame++;
    assert(legacyAxisRaw(&name)==1 && legacyAxisRaw(&name)==1);
    frame++;assert(legacyAxisRaw(&name)==0);
    // A quick press/release between polls must retain both edges for one frame.
    keys[37/8]|=1u<<(37%8);sendKeyboard();
    memset(keys,0,sizeof(keys));sendKeyboard();frame++;
    assert(legacyKeyDown('w') && legacyKeyUp('w') && !legacyKeyHeld('w'));
    frame++;assert(!legacyKeyDown('w') && !legacyKeyUp('w'));
    assert(legacyPositiveKeys>0 && legacyPositiveScrolls>0 && legacyNamedAxes>0);
}
