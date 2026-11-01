#include "../src/MousePresence.h"
#include <assert.h>

static bool ready;
static unsigned nativeCalls;
static MousePresentCallback original;
static bool nativePresence(void) { nativeCalls++; return false; }
static bool bridgePresence(void) { return ready || (original && original()); }

int main(void) {
    MousePresentCallback slot=nativePresence;
    assert(installMousePresence(&slot, bridgePresence, &original));
    assert(original==nativePresence);
    assert(!slot() && nativeCalls==1);
    ready=true;
    assert(slot() && nativeCalls==1);
    assert(!installMousePresence(&slot, bridgePresence, &original));
    assert(original==nativePresence); // Re-entry must not save the bridge as its own fallback.
    ready=false;
    assert(!slot() && nativeCalls==2);
    slot=0;
    assert(!installMousePresence(&slot, bridgePresence, &original));
    assert(!installMousePresence(0, bridgePresence, &original));
}
