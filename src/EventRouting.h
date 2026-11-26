#ifndef NATIVE_EVENT_ROUTING_H
#define NATIVE_EVENT_ROUTING_H
#import <Foundation/Foundation.h>

@interface NSObject (BridgeEventRouting)
- (id)firstResponder;
- (BOOL)isEditable;
- (BOOL)isEnabled;
@end

static inline BOOL routeGameEvent(id window, id gameWindow) {
    if (!gameWindow || window != gameWindow) return NO;
    id responder=[window firstResponder];
    if (!responder) return YES;
    for (NSString *name in @[@"NSText", @"NSTextField"]) {
        Class textClass=NSClassFromString(name);
        if (textClass && [responder isKindOfClass:textClass]) {
            if ([responder respondsToSelector:@selector(isEditable)] && ![responder isEditable]) return YES;
            if ([responder respondsToSelector:@selector(isEnabled)] && ![responder isEnabled]) return YES;
            return NO;
        }
    }
    Class uiInput=NSClassFromString(@"UINSInputView");
    if (!uiInput || ![responder isKindOfClass:uiInput]) {
        for (NSString *protoName in @[@"NSTextInputClient", @"NSTextInput"]) {
            Protocol *proto=NSProtocolFromString(protoName);
            if (proto && [responder conformsToProtocol:proto]) return NO;
        }
    }
    return YES;
}
#endif
