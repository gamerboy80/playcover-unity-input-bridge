#include <assert.h>
#include <stdint.h>
#define GameFieldStaticFields 8
static uintptr_t slide;
#include "../src/InputSystemStatics.h"
int main(void) {
    uintptr_t reference=0, fields[]={42, 99}, type[]={0, 0};
    assert(inputStatic((uintptr_t)&reference,0)==0);
#if GameTypeStatics
    reference=0x2003abf1;
    assert(inputStatic((uintptr_t)&reference,0)==0);
    reference=(uintptr_t)type;
    assert(inputStatic((uintptr_t)&reference,0)==0);
    type[1]=(uintptr_t)fields;
#else
    (void)type;
    reference=(uintptr_t)fields;
#endif
    assert(inputStatic((uintptr_t)&reference,0)==42);
    assert(inputStatic((uintptr_t)&reference,8)==99);
}
