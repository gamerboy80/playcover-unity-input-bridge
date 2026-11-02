#ifndef NATIVE_EVENT_ROUTING_H
#define NATIVE_EVENT_ROUTING_H
#import <Foundation/Foundation.h>

@interface NSObject (BridgeEventRouting)
- (id)firstResponder;
@end

static inline BOOL routeGameEvent(id window, id gameWindow) {
    if (!gameWindow || window != gameWindow) return NO;
    id responder=[window firstResponder];
    for (NSString *name in @[@"NSText", @"NSTextField"]) {
        Class textClass=NSClassFromString(name);
        if (textClass && [responder isKindOfClass:textClass]) return NO;
    }
    return YES;
}
#endif
