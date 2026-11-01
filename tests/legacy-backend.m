#import <Foundation/Foundation.h>
#include <assert.h>
#include "../src/InputState.h"
#include "../src/Scroll.h"
static uintptr_t slide;
static uint8_t keys[14];
static MouseState mouseState;
static int frame, setCode, setHeld;
static void *slots[7];
static int frameCount(void) { return frame; }
static void setKey(unsigned code,BOOL held) { setCode=(int)code; setHeld=held; }
static BOOL button(int b) { return b==4; }
static float axis(void *s) { (void)s; return 7; }
static void position(float *p) { p[0]=5;p[1]=6;p[2]=0; }
#define GameFrameCount ((uintptr_t)frameCount)
#define GameSetKey ((uintptr_t)setKey)
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
    assert(initializeLegacy());
    assert(legacyKey(37)=='w' && legacyKey(94)==282 && legacyKey(105)==293);
    keys[37/8]|=1u<<(37%8); sendKeyboard();
    assert(setCode=='w' && setHeld);
    memset(keys,0,sizeof(keys));sendKeyboard();assert(setCode=='w' && !setHeld);
    mouseState=(MouseState){.x=100,.y=200,.buttons=1,.sx=120,.sy=-240};sendMouse();
    float p[3];legacyPosition(p);assert(p[0]==100 && p[1]==200);
    assert(legacyDown(0) && legacyDown(0) && legacyHeld(0));
    float scroll[2];legacyScroll(scroll);assert(scroll[0]==1 && scroll[1]==-2);
    legacyScroll(scroll);assert(scroll[1]==-2); // Polling twice must not consume the frame.
    frame++;legacyScroll(scroll);assert(scroll[1]==0 && !legacyDown(0));
    mouseState.buttons=0;sendMouse();frame++;assert(legacyUp(0) && !legacyHeld(0));
    frame++;assert(!legacyUp(0));
    assert(legacyHeld(4)); // Preserve unrelated native mouse input.
    assert(legacyAxisRaw(NULL)==7);
}
