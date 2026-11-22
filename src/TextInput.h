#pragma once
#import <UIKit/UIKit.h>

static BOOL editingUIKitText(UIView *view) {
    // WebKit and custom text responders need native key events too, even when empty.
    if (view.isFirstResponder && [view conformsToProtocol:@protocol(UIKeyInput)]) return YES;
    for (UIView *child in view.subviews) if (editingUIKitText(child)) return YES;
    return NO;
}
