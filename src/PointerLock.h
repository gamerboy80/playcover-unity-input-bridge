#ifndef NATIVE_POINTER_LOCK_H
#define NATIVE_POINTER_LOCK_H
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#include <string.h>

static inline BOOL restoreNativePointerLock(Class controller) {
    if (!controller) return NO;
    SEL preference=sel_registerName("prefersPointerLocked");
    SEL alias=sel_registerName("hook_prefersPointerLocked");
    Method current=class_getInstanceMethod(controller,preference);
    Method saved=class_getInstanceMethod(controller,alias);
    Method blocker=class_getInstanceMethod(NSObject.class,alias);
    Method inherited=class_getInstanceMethod(class_getSuperclass(controller),alias);
    // PlayTools saves Unity's implementation on the controller, leaving its blocker on NSObject.
    if (!current || !saved || !blocker || saved==inherited ||
        method_getImplementation(current)!=method_getImplementation(blocker) ||
        method_getImplementation(saved)==method_getImplementation(blocker) ||
        strcmp(method_getTypeEncoding(current),method_getTypeEncoding(saved))!=0) return NO;
    class_replaceMethod(controller,preference,method_getImplementation(saved),method_getTypeEncoding(saved));
    return YES;
}
#endif
