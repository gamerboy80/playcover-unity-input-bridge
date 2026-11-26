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
@property BOOL testFirstResponder;
@end
@implementation FocusTextField
- (instancetype)init {
    if ((self = [super init])) _testFirstResponder = YES;
    return self;
}
- (BOOL)isFirstResponder { return self.testFirstResponder; }
@end

@interface FocusTextView : UITextView
@property BOOL testFirstResponder;
@end
@implementation FocusTextView
- (instancetype)init {
    if ((self = [super init])) _testFirstResponder = YES;
    return self;
}
- (BOOL)isFirstResponder { return self.testFirstResponder; }
@end

@interface FocusSearchTextField : UISearchTextField
@property BOOL testFirstResponder;
@end
@implementation FocusSearchTextField
- (instancetype)init {
    if ((self = [super init])) _testFirstResponder = YES;
    return self;
}
- (BOOL)isFirstResponder { return self.testFirstResponder; }
@end

@interface NonViewTextResponder : UIResponder <UIKeyInput>
@property BOOL testFirstResponder;
@end
@implementation NonViewTextResponder
- (BOOL)isFirstResponder { return self.testFirstResponder; }
- (BOOL)hasText { return NO; }
- (void)insertText:(NSString *)text { (void)text; }
- (void)deleteBackward {}
@end

@interface TextViewController : UIViewController <UIKeyInput>
@property BOOL testFirstResponder;
@end
@implementation TextViewController
- (BOOL)isFirstResponder { return self.testFirstResponder; }
- (BOOL)hasText { return NO; }
- (void)insertText:(NSString *)text { (void)text; }
- (void)deleteBackward {}
@end

@interface TestScene : NSObject
@property UISceneActivationState activationState;
@property(copy) NSArray *windows;
@end
@implementation TestScene
@end

@interface TestHostResponder : NSObject
@property(strong) id hostedResponder;
- (id)_hostedFirstResponder;
@end
@implementation TestHostResponder
- (id)_hostedFirstResponder { return self.hostedResponder; }
@end

@interface TestHostWindow : NSObject
@property(strong) id firstResponder;
@end
@implementation TestHostWindow
@end

int main(void) {
    @autoreleasepool {
        assert(!editingUIKitText(nil));
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
        input.userInteractionEnabled=NO;
        assert(!editingUIKitText(root));
        input.userInteractionEnabled=YES;
        container.hidden=YES;
        assert(!editingUIKitText(root)); // Hidden containers must not keep input focused.
        container.hidden=NO;
        assert(editingUIKitText(root));
        input.testFirstResponder=NO;
        root.testFirstResponder=YES;
        assert(!editingUIKitText(root)); // Resume gameplay after editing ends.

        FocusTextField *field=[FocusTextField new];
        assert(editingUIKitText(field));
        field.hidden=YES;
        assert(editingUIKitText(field)); // Unity TouchScreenKeyboard.hideInput hides the UITextField itself.
        field.hidden=NO;
        field.enabled=NO;
        assert(!editingUIKitText(field));
        FocusView *fieldHolder=[FocusView new];
        field.enabled=YES;
        [fieldHolder addSubview:field];
        fieldHolder.hidden=YES;
        assert(!editingUIKitText(fieldHolder));

        FocusTextView *textView=[FocusTextView new];
        assert(editingUIKitText(textView));
        textView.editable=NO;
        textView.selectable=YES;
        assert(!editingUIKitText(textView)); // Read-only selectable UITextViews must not steal game keys.
        textView.editable=YES;
        textView.userInteractionEnabled=NO;
        assert(!editingUIKitText(textView));

        FocusSearchTextField *search=[FocusSearchTextField new];
        assert(editingUIKitText(search));
        search.enabled=NO;
        assert(!editingUIKitText(search));

        TextViewController *vc=[TextViewController new];
        [root addSubview:vc.view];
        vc.testFirstResponder=YES;
        assert(editingUIKitText(root));
        vc.testFirstResponder=NO;
        assert(!editingUIKitText(root));

        FocusView *overlayWindow=[FocusView new];
        FocusTextField *overlayField=[FocusTextField new];
        [overlayWindow addSubview:overlayField];
        TestScene *bgScene=[TestScene new], *activeScene=[TestScene new];
        bgScene.activationState=UISceneActivationStateBackground;
        bgScene.windows=@[overlayWindow];
        assert(!editingUIKitScenes(@[bgScene], nil));

        bgScene.activationState=UISceneActivationStateForegroundInactive;
        assert(editingUIKitScenes(@[bgScene], nil)); // Fallback when no scene is ForegroundActive.
        activeScene.activationState=UISceneActivationStateForegroundActive;
        activeScene.windows=@[[FocusView new]];
        assert(!editingUIKitScenes(@[bgScene, activeScene], nil)); // Inactive scenes do not block the active one.

        activeScene.windows=@[overlayWindow];
        assert(editingUIKitScenes(@[activeScene], nil)); // Visible non-key overlay windows still count.
        overlayWindow.hidden=YES;
        assert(!editingUIKitScenes(@[activeScene], nil));

        NonViewTextResponder *nonView=[NonViewTextResponder new];
        nonView.testFirstResponder=YES;
        TestHostResponder *hostResponder=[TestHostResponder new];
        hostResponder.hostedResponder=nonView;
        TestHostWindow *hostWindow=[TestHostWindow new];
        hostWindow.firstResponder=hostResponder;
        assert(editingUIKitScenes(@[], hostWindow));
        nonView.testFirstResponder=NO;
        assert(!editingUIKitScenes(@[], hostWindow));
        puts("UIKit text focus checks passed");
    }
}
