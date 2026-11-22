#include "../src/TextInput.h"
#include <assert.h>

@interface FocusView : UIView
@property BOOL testFirstResponder;
@end
@implementation FocusView
- (BOOL)isFirstResponder { return self.testFirstResponder; }
@end

// WebKit's content view adopts text-input protocols, not UITextField/UITextView.
@interface WebTextInput : FocusView <UIKeyInput>
@end
@implementation WebTextInput
- (BOOL)hasText { return NO; }
- (void)insertText:(NSString *)text { (void)text; }
- (void)deleteBackward {}
@end

@interface FocusTextField : UITextField
@end
@implementation FocusTextField
- (BOOL)isFirstResponder { return YES; }
@end

@interface FocusTextView : UITextView
@end
@implementation FocusTextView
- (BOOL)isFirstResponder { return YES; }
@end

int main(void) {
    @autoreleasepool {
        FocusView *root=[FocusView new], *container=[FocusView new];
        WebTextInput *input=[WebTextInput new];
        [root addSubview:container];
        [container addSubview:input];
        root.testFirstResponder=YES;
        assert(!editingUIKitText(root)); // A focused game view must retain gameplay keys.
        root.testFirstResponder=NO;
        assert(!editingUIKitText(root)); // An unfocused text view must not steal them.
        input.testFirstResponder=YES;
        assert(!input.hasText); // Empty verification fields still need the first keystroke.
        assert(editingUIKitText(root));
        input.testFirstResponder=NO;
        root.testFirstResponder=YES;
        assert(!editingUIKitText(root)); // Resume gameplay after editing ends.
        assert(editingUIKitText([FocusTextField new]));
        assert(editingUIKitText([FocusTextView new]));
        puts("UIKit text focus checks passed");
    }
}
