#pragma once
#import <UIKit/UIKit.h>

@interface NSObject (BridgeUIKitTextInput)
- (id)firstResponder;
- (id)_hostedFirstResponder;
@end

static inline BOOL editingUIKitResponder(id responder) {
    if (![responder isKindOfClass:UIResponder.class]) return NO;
    UIResponder *target = responder;
    if (!target.isFirstResponder || ![target conformsToProtocol:@protocol(UIKeyInput)]) return NO;
    if ([target isKindOfClass:UIView.class]) {
        Class wkContent = NSClassFromString(@"WKContentView");
        Class wkWebView = NSClassFromString(@"WKWebView");
        for (UIView *v = (UIView *)target; v; v = v.superview) {
            if (!v.isUserInteractionEnabled) return NO;
            if ([v isKindOfClass:UITextView.class] && !((UITextView *)v).isEditable) return NO;
            if ([v isKindOfClass:UIControl.class] && !((UIControl *)v).isEnabled) return NO;
            if (v.hidden && ![v isKindOfClass:UITextField.class] && ![v isKindOfClass:UITextView.class]) {
                if (v != (UIView *)target || (wkContent && [v isKindOfClass:wkContent]) ||
                    (wkWebView && [v isKindOfClass:wkWebView])) {
                    return NO;
                }
            }
        }
    }
    return YES;
}

static inline BOOL editingUIKitText(UIView *view) {
    if (!view) return NO;
    if (!view.isUserInteractionEnabled) return NO;
    if ([view isKindOfClass:UIControl.class] && !((UIControl *)view).isEnabled) return NO;
    Class wkWebView = NSClassFromString(@"WKWebView");
    if (wkWebView && [view isKindOfClass:wkWebView] && view.hidden) return NO;
    if ([view isKindOfClass:UIWindow.class] && [view respondsToSelector:@selector(firstResponder)]) {
        id responder = [view firstResponder];
        if (responder) return editingUIKitResponder(responder);
    }
    // WebKit and custom text responders need native key events too, even when empty.
    if (editingUIKitResponder(view)) return YES;
    unsigned hops = 0;
    for (UIResponder *next = view.nextResponder;
         next && ![next isKindOfClass:UIView.class] && hops < 16;
         next = next.nextResponder, hops++) {
        if (editingUIKitResponder(next)) return YES;
    }
    if (view.hidden && ![view isKindOfClass:UITextField.class] && ![view isKindOfClass:UITextView.class]) {
        return NO;
    }
    for (UIView *child in view.subviews) if (editingUIKitText(child)) return YES;
    return NO;
}

static inline BOOL editingUIKitScenes(id scenes, id hostWindow) {
    if (hostWindow && [hostWindow respondsToSelector:@selector(firstResponder)]) {
        id hostResponder = [hostWindow firstResponder];
        if ([hostResponder respondsToSelector:@selector(_hostedFirstResponder)] &&
            editingUIKitResponder([hostResponder _hostedFirstResponder])) {
            return YES;
        }
    }
    BOOL hasForegroundActive = NO;
    for (id scene in scenes) {
        if (![scene respondsToSelector:@selector(windows)] ||
            ![scene respondsToSelector:@selector(activationState)]) continue;
        UIWindowScene *windowScene = (UIWindowScene *)scene;
        if (windowScene.activationState == UISceneActivationStateForegroundActive) {
            hasForegroundActive = YES;
            break;
        }
    }
    for (id scene in scenes) {
        if (![scene respondsToSelector:@selector(windows)] ||
            ![scene respondsToSelector:@selector(activationState)]) continue;
        UIWindowScene *windowScene = (UIWindowScene *)scene;
        UISceneActivationState state = windowScene.activationState;
        if (state == UISceneActivationStateBackground || state == UISceneActivationStateUnattached) continue;
        if (hasForegroundActive && state != UISceneActivationStateForegroundActive) continue;
        for (UIView *window in windowScene.windows) {
            if ([window isKindOfClass:UIView.class] && !window.hidden && editingUIKitText(window)) return YES;
        }
    }
    return NO;
}
