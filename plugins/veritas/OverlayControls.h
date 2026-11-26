@interface VeritasPanel : UIView
@property(nonatomic, strong) UIStackView *stack;
@property(nonatomic, strong) UILabel *title;
@property(nonatomic, strong) UIButton *settings;
@property(nonatomic, strong) UIButton *resize;
@property(nonatomic, copy) NSString *identifier;
@property(nonatomic) BOOL editing;
@end

@implementation VeritasPanel {
    CGRect _gestureStart;
    UIPanGestureRecognizer *_moveGesture;
}

- (instancetype)initWithTitle:(NSString *)title identifier:(NSString *)identifier {
    if (!(self = [super initWithFrame:CGRectZero])) return nil;
    self.identifier = identifier;
    self.layer.cornerRadius = 10;
    self.clipsToBounds = YES;
    self.title = [UILabel new];
    self.title.text = title;
    self.settings = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.settings setImage:[UIImage systemImageNamed:@"gearshape"] forState:UIControlStateNormal];
    self.settings.accessibilityLabel = @"Overlay settings";
    self.settings.showsMenuAsPrimaryAction = YES;
    UIStackView *heading = [[UIStackView alloc] initWithArrangedSubviews:@[self.title, self.settings]];
    heading.alignment = UIStackViewAlignmentCenter;
    _moveGesture = [[UIPanGestureRecognizer alloc] initWithTarget:self action:@selector(move:)];
    [heading addGestureRecognizer:_moveGesture];
    self.stack = [[UIStackView alloc] initWithArrangedSubviews:@[heading]];
    self.stack.axis = UILayoutConstraintAxisVertical;
    self.stack.spacing = 6;
    self.stack.translatesAutoresizingMaskIntoConstraints = NO;
    [self addSubview:self.stack];
    [NSLayoutConstraint activateConstraints:@[
        [self.stack.leadingAnchor constraintEqualToAnchor:self.leadingAnchor constant:8],
        [self.stack.trailingAnchor constraintEqualToAnchor:self.trailingAnchor constant:-8],
        [self.stack.topAnchor constraintEqualToAnchor:self.topAnchor constant:10],
        [self.stack.bottomAnchor constraintEqualToAnchor:self.bottomAnchor constant:-10],
    ]];
    self.resize = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.resize setImage:[UIImage systemImageNamed:@"arrow.up.left.and.arrow.down.right"] forState:UIControlStateNormal];
    self.resize.accessibilityLabel = @"Resize panel";
    self.resize.translatesAutoresizingMaskIntoConstraints = NO;
    [self.resize addGestureRecognizer:[[UIPanGestureRecognizer alloc] initWithTarget:self action:@selector(resizePanel:)]];
    [self addSubview:self.resize];
    [NSLayoutConstraint activateConstraints:@[
        [self.resize.trailingAnchor constraintEqualToAnchor:self.trailingAnchor constant:-4],
        [self.resize.bottomAnchor constraintEqualToAnchor:self.bottomAnchor constant:-4],
        [self.resize.widthAnchor constraintEqualToConstant:26],
        [self.resize.heightAnchor constraintEqualToConstant:26],
    ]];
    self.editing = NO;
    return self;
}

- (void)setEditing:(BOOL)editing {
    _editing = editing;
    self.resize.hidden = !editing;
    _moveGesture.enabled = editing;
}

- (void)applyPan:(UIPanGestureRecognizer *)pan resize:(BOOL)resize {
    if (!self.editing || !self.superview) return;
    if (pan.state == UIGestureRecognizerStateBegan) {
        _gestureStart = self.frame;
        [self.superview bringSubviewToFront:self];
    }
    CGRect bounds = self.superview.safeAreaLayoutGuide.layoutFrame;
    CGPoint shift = [pan translationInView:self.superview];
    CGRect frame = _gestureStart;
    if (resize) {
        frame.size.width = MIN(MAX(240, frame.size.width + shift.x), CGRectGetMaxX(bounds) - frame.origin.x);
        frame.size.height = MIN(MAX(130, frame.size.height + shift.y), CGRectGetMaxY(bounds) - frame.origin.y);
    } else {
        frame.origin.x = MAX(CGRectGetMinX(bounds), MIN(CGRectGetMaxX(bounds) - frame.size.width, frame.origin.x + shift.x));
        frame.origin.y = MAX(CGRectGetMinY(bounds), MIN(CGRectGetMaxY(bounds) - frame.size.height, frame.origin.y + shift.y));
    }
    self.frame = frame;
    if (pan.state == UIGestureRecognizerStateEnded || pan.state == UIGestureRecognizerStateCancelled) {
        [NSUserDefaults.standardUserDefaults setObject:NSStringFromCGRect(frame) forKey:self.identifier];
    }
}

- (void)move:(UIPanGestureRecognizer *)pan { [self applyPan:pan resize:NO]; }
- (void)resizePanel:(UIPanGestureRecognizer *)pan { [self applyPan:pan resize:YES]; }

- (void)layoutWithin:(CGRect)bounds defaultFrame:(CGRect)defaultFrame {
    NSString *saved = [NSUserDefaults.standardUserDefaults stringForKey:self.identifier];
    CGRect frame = saved ? CGRectFromString(saved) : defaultFrame;
    if (CGRectIsEmpty(frame)) frame = defaultFrame;
    frame.size.width = MIN(frame.size.width, bounds.size.width);
    frame.size.height = MIN(frame.size.height, bounds.size.height);
    frame.origin.x = MAX(CGRectGetMinX(bounds), MIN(frame.origin.x, CGRectGetMaxX(bounds) - frame.size.width));
    frame.origin.y = MAX(CGRectGetMinY(bounds), MIN(frame.origin.y, CGRectGetMaxY(bounds) - frame.size.height));
    self.frame = frame;
}

@end

@interface VeritasOverlayLayout : UIViewController
@property(nonatomic, copy) void (^updatePanels)(CGRect);
@end

@implementation VeritasOverlayLayout
- (void)viewDidLayoutSubviews {
    [super viewDidLayoutSubviews];
    if (self.updatePanels) self.updatePanels(self.view.safeAreaLayoutGuide.layoutFrame);
}
@end

@interface VeritasPassthroughWindow : UIWindow
@property(nonatomic) BOOL editing;
@end

@implementation VeritasPassthroughWindow
- (UIView *)hitTest:(CGPoint)point withEvent:(UIEvent *)event {
    UIView *hit = [super hitTest:point withEvent:event];
    if (self.rootViewController.presentedViewController) return hit;
    for (UIView *view = hit; view; view = view.superview) {
        if (self.editing ? [view isKindOfClass:VeritasPanel.class] : [view isKindOfClass:UIControl.class]) return hit;
    }
    return nil;
}
@end
