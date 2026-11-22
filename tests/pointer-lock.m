#import <Foundation/Foundation.h>
#include <assert.h>
#include "../src/PointerLock.h"

@interface NSObject (TestPointerBlocker)
- (BOOL)hook_prefersPointerLocked;
@end
@implementation NSObject (TestPointerBlocker)
- (BOOL)hook_prefersPointerLocked { return NO; }
@end

@interface PointerController : NSObject
@property BOOL wantsLock;
- (BOOL)prefersPointerLocked;
@end
@implementation PointerController
- (BOOL)prefersPointerLocked { return self.wantsLock; }
@end

static BOOL foreignPreference(id object, SEL selector) {
    (void)object; (void)selector;
    return NO;
}

static Class controllerClass(const char *name, BOOL ownPreference) {
    Class cls=objc_allocateClassPair(PointerController.class,name,0);
    assert(cls);
    if (ownPreference) {
        Method method=class_getInstanceMethod(PointerController.class,@selector(prefersPointerLocked));
        assert(class_addMethod(cls,@selector(prefersPointerLocked),method_getImplementation(method),method_getTypeEncoding(method)));
    }
    objc_registerClassPair(cls);
    return cls;
}

static void simulatePlayTools(Class cls) {
    SEL preference=@selector(prefersPointerLocked), alias=@selector(hook_prefersPointerLocked);
    Method original=class_getInstanceMethod(cls,preference);
    Method blocker=class_getInstanceMethod(NSObject.class,alias);
    IMP saved=method_getImplementation(original);
    const char *types=method_getTypeEncoding(original);
    class_replaceMethod(cls,preference,method_getImplementation(blocker),method_getTypeEncoding(blocker));
    class_replaceMethod(cls,alias,saved,types);
}

int main(void) {
    @autoreleasepool {
        assert(!restoreNativePointerLock(Nil));
        assert(!restoreNativePointerLock(NSObject.class));
        assert(!restoreNativePointerLock(PointerController.class)); // Already patched PlayTools or no PlayTools.
        for (unsigned own=0;own<2;own++) {
            Class cls=controllerClass(own ? "OwnPreference" : "InheritedPreference",own);
            simulatePlayTools(cls);
            PointerController *controller=[cls new];
            controller.wantsLock=YES;
            assert(!controller.prefersPointerLocked);
            assert(restoreNativePointerLock(cls));
            assert(controller.prefersPointerLocked);
            controller.wantsLock=NO;
            assert(!controller.prefersPointerLocked); // Preserve Unity's menu/gameplay decision.
            assert(!restoreNativePointerLock(cls)); // Repeated calls must not reinstate the blocker.
            assert(![controller hook_prefersPointerLocked]);
            assert(![[NSObject new] hook_prefersPointerLocked]);
        }
        Class foreign=controllerClass("ForeignPreference",YES);
        simulatePlayTools(foreign);
        class_replaceMethod(foreign,@selector(prefersPointerLocked),(IMP)foreignPreference,"B@:");
        assert(!restoreNativePointerLock(foreign));
        assert(class_getMethodImplementation(foreign,@selector(prefersPointerLocked))==(IMP)foreignPreference);
        Class mismatch=controllerClass("MismatchedPreference",YES);
        assert(class_addMethod(mismatch,@selector(hook_prefersPointerLocked),(IMP)foreignPreference,"i@:"));
        Method blocker=class_getInstanceMethod(NSObject.class,@selector(hook_prefersPointerLocked));
        class_replaceMethod(mismatch,@selector(prefersPointerLocked),method_getImplementation(blocker),method_getTypeEncoding(blocker));
        assert(!restoreNativePointerLock(mismatch));
        Class missing=controllerClass("MissingOriginal",YES);
        class_replaceMethod(missing,@selector(prefersPointerLocked),method_getImplementation(blocker),method_getTypeEncoding(blocker));
        assert(!restoreNativePointerLock(missing));
    }
    return 0;
}
