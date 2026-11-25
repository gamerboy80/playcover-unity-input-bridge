#import "DashboardData.h"
#import "../veritas/OverlayControls.h"

static UIColor *ZZZChartColor(NSUInteger index) {
    static const unsigned palette[] = {0xff6384, 0x36a2eb, 0xffce56, 0x4bc0c0, 0x9966ff, 0xff9f40};
    unsigned rgb = palette[index % 6];
    return [UIColor colorWithRed:(rgb >> 16) / 255.0 green:((rgb >> 8) & 255) / 255.0 blue:(rgb & 255) / 255.0 alpha:1];
}
@interface ZZZChart : UIView
@property(nonatomic, copy) NSDictionary *snapshot;
@property(nonatomic) NSInteger mode;
@property(nonatomic, strong) UIColor *textColor;
@property(nonatomic) CGFloat textSize;
@property(nonatomic) BOOL aliases;
@end
@implementation ZZZChart
- (void)setSnapshot:(NSDictionary *)snapshot { _snapshot = snapshot; [self setNeedsDisplay]; }
- (void)text:(NSString *)text rect:(CGRect)rect {
    [text drawInRect:rect withAttributes:@{NSFontAttributeName: [UIFont monospacedDigitSystemFontOfSize:self.textSize weight:UIFontWeightRegular],
        NSForegroundColorAttributeName: self.textColor ?: UIColor.whiteColor}];
}
- (void)drawRect:(CGRect)dirty {
    (void)dirty;
    CGRect area = CGRectInset(self.bounds, 4, 4);
    NSArray *sources = self.snapshot[@"sources"];
    double total = [self.snapshot[@"total"] doubleValue];
    if (total <= 0) { [self text:@"Waiting for damage" rect:area]; return; }
    if (self.mode == 2) {
        NSArray *points = self.snapshot[@"timeline"];
        double seconds = MAX(1, [self.snapshot[@"seconds"] doubleValue]);
        [self text:@"Cumulative raw damage · game seconds" rect:area];
        area.origin.y += 26; area.size.height -= 48;
        UIBezierPath *path = [UIBezierPath bezierPath];
        BOOL first = YES;
        for (NSDictionary *point in points) {
            CGPoint position = CGPointMake(area.origin.x + area.size.width * [point[@"time"] doubleValue] / seconds,
                CGRectGetMaxY(area) - area.size.height * [point[@"total"] doubleValue] / total);
            if (first) [path moveToPoint:position]; else [path addLineToPoint:position];
            first = NO;
        }
        [ZZZChartColor(1) setStroke]; path.lineWidth = 2; [path stroke];
        [self text:[NSString stringWithFormat:@"0 — %.1f s     %.0f raw", seconds, total]
            rect:CGRectMake(area.origin.x, CGRectGetMaxY(area) + 4, area.size.width, 22)];
        return;
    }
    if (self.mode == 1) {
        CGFloat radius = MAX(1, MIN(area.size.width * 0.27, area.size.height * 0.44));
        CGPoint center = CGPointMake(area.origin.x + radius, CGRectGetMidY(area));
        CGFloat start = -M_PI_2;
        NSUInteger index = 0;
        for (NSDictionary *source in sources) {
            CGFloat end = start + [source[@"damage"] doubleValue] / total * M_PI * 2;
            UIBezierPath *slice = [UIBezierPath bezierPath];
            [slice moveToPoint:center]; [slice addArcWithCenter:center radius:radius startAngle:start endAngle:end clockwise:YES];
            [slice closePath]; [[ZZZChartColor(index++) colorWithAlphaComponent:0.85] setFill]; [slice fill]; start = end;
        }
        CGFloat y = area.origin.y;
        index = 0;
        for (NSDictionary *source in sources) {
            if (y + 22 > CGRectGetMaxY(area)) break;
            [ZZZChartColor(index) setFill]; UIRectFill(CGRectMake(center.x + radius + 10, y + 4, 8, 8));
            NSString *name = self.aliases ? [NSString stringWithFormat:@"Source %lu", (unsigned long)index + 1] : source[@"name"];
            [self text:[NSString stringWithFormat:@"%@  %.1f%%", name, [source[@"damage"] doubleValue] / total * 100]
                rect:CGRectMake(center.x + radius + 24, y, MAX(0, area.size.width - radius * 2 - 24), 22)];
            index++; y += self.textSize + 10;
        }
        return;
    }
    double maximum = 1;
    for (NSDictionary *source in sources) maximum = MAX(maximum, [source[@"damage"] doubleValue]);
    CGFloat y = area.origin.y;
    NSUInteger index = 0;
    for (NSDictionary *source in sources) {
        if (y + 40 > CGRectGetMaxY(area)) break;
        double damage = [source[@"damage"] doubleValue];
        NSString *name = self.aliases ? [NSString stringWithFormat:@"Source %lu", (unsigned long)index + 1] : source[@"name"];
        [self text:[NSString stringWithFormat:@"%@  %.0f · %.1f%%", name, damage, damage / total * 100]
            rect:CGRectMake(area.origin.x, y, area.size.width, 22)];
        [ZZZChartColor(index++) setFill];
        UIRectFill(CGRectMake(area.origin.x, y + 25, area.size.width * damage / maximum, 6));
        y += MAX(42, self.textSize + 28);
    }
}
@end

@interface ZZZDashboardWindow : UIWindow
@property(nonatomic) BOOL editing;
@end
@implementation ZZZDashboardWindow
- (UIView *)hitTest:(CGPoint)point withEvent:(UIEvent *)event {
    UIView *hit = [super hitTest:point withEvent:event];
    if (self.rootViewController.presentedViewController) return hit;
    for (UIView *view = hit; view; view = view.superview)
        if (self.editing ? [view isKindOfClass:VeritasPanel.class] : [view isKindOfClass:UIControl.class]) return hit;
    return nil;
}
@end

@interface ZZZDashboard : NSObject
@property(nonatomic, strong) ZZZDashboardWindow *window;
@property(nonatomic, weak) UIWindow *game;
@property(nonatomic, strong) NSArray<VeritasPanel *> *panels;
@property(nonatomic, strong) UILabel *metrics;
@property(nonatomic, strong) UITextView *details;
@property(nonatomic, strong) NSArray<ZZZChart *> *charts;
@property(nonatomic, strong) NSDictionary *live, *selected;
@property(nonatomic, strong) NSMutableArray *history;
@property(nonatomic, copy) NSString *session;
@property(nonatomic) BOOL archived, editing;
@property(nonatomic, strong) UIMenu *controls;
@property(nonatomic, strong) dispatch_queue_t storageQueue;
- (void)update:(NSDictionary *)snapshot game:(UIWindow *)game visible:(BOOL)visible;
- (void)toggleEditing;
- (void)saveSnapshot:(NSDictionary *)snapshot;
@end
@implementation ZZZDashboard
- (instancetype)init {
    if ((self = [super init])) {
        [NSUserDefaults.standardUserDefaults registerDefaults:@{@"ZZZDamage.Opacity": @0.86, @"ZZZDamage.Font": @13}];
        NSURL *documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
        NSData *data = [NSData dataWithContentsOfURL:[documents URLByAppendingPathComponent:@"ZZZDamage/history.json"]];
        id stored = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:NULL] : nil;
        _history = [NSMutableArray array];
        _storageQueue = dispatch_queue_create("ZZZDamage.history", DISPATCH_QUEUE_SERIAL);
        if ([stored isKindOfClass:NSArray.class]) for (id row in stored) {
            if (_history.count >= 20) break;
            if ([row isKindOfClass:NSDictionary.class] && [row[@"schema"] isEqual:@1] &&
                [row[@"sources"] isKindOfClass:NSArray.class] && [row[@"timeline"] isKindOfClass:NSArray.class]) [_history addObject:row];
        }
    }
    return self;
}
- (UIAction *)action:(NSString *)name block:(void (^)(void))block {
    return [UIAction actionWithTitle:name image:nil identifier:nil handler:^(__unused UIAction *action) { block(); }];
}
- (UIAction *)setting:(NSString *)name key:(NSString *)key value:(id)value {
    NSUserDefaults *prefs = NSUserDefaults.standardUserDefaults;
    UIAction *action = [self action:name block:^{
        [prefs setObject:value ?: @(![prefs boolForKey:key]) forKey:key]; [self apply];
    }];
    action.state = (value ? [[prefs objectForKey:key] isEqual:value] : [prefs boolForKey:key]) ? UIMenuElementStateOn : UIMenuElementStateOff;
    return action;
}
- (void)share:(BOOL)csv {
    NSDictionary *snapshot = self.selected ?: self.live;
    if (!snapshot) return;
    NSError *error = nil;
    NSURL *file = ZZZWriteSummary(snapshot, csv, &error);
    UIViewController *controller;
    if (file) {
        controller = [[UIActivityViewController alloc] initWithActivityItems:@[file] applicationActivities:nil];
        controller.popoverPresentationController.sourceView = self.panels.firstObject.settings;
        controller.popoverPresentationController.sourceRect = self.panels.firstObject.settings.bounds;
    } else {
        UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"Export failed" message:error.localizedDescription preferredStyle:UIAlertControllerStyleAlert];
        [alert addAction:[UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleDefault handler:nil]];
        controller = alert;
    }
    [self.window.rootViewController presentViewController:controller animated:YES completion:nil];
}
- (void)archive {
    if (self.archived || [self.live[@"total"] doubleValue] <= 0) return;
    self.archived = YES;
    [self saveSnapshot:self.live];
}
- (void)saveSnapshot:(NSDictionary *)snapshot {
    if ([snapshot[@"total"] doubleValue] <= 0) return;
    for (NSDictionary *saved in self.history) if ([saved[@"session"] isEqual:snapshot[@"session"]]) return;
    [self.history insertObject:snapshot atIndex:0];
    if (self.history.count > 20) [self.history removeLastObject];
    NSArray *history = [self.history copy];
    BOOL autosave = [NSUserDefaults.standardUserDefaults boolForKey:@"ZZZDamage.Autosave"];
    dispatch_async(self.storageQueue, ^{
        NSURL *documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
        NSURL *folder = [documents URLByAppendingPathComponent:@"ZZZDamage" isDirectory:YES];
        NSError *error = nil;
        BOOL ok = [NSFileManager.defaultManager createDirectoryAtURL:folder withIntermediateDirectories:YES attributes:nil error:&error];
        NSData *data = ok ? [NSJSONSerialization dataWithJSONObject:history options:0 error:&error] : nil;
        ok = data && [data writeToURL:[folder URLByAppendingPathComponent:@"history.json"] options:NSDataWritingAtomic error:&error];
        if (autosave) ok = ZZZWriteSummary(snapshot, NO, &error) && ZZZWriteSummary(snapshot, YES, &error) && ok;
        if (!ok) NSLog(@"[ZZZDamage] Save failed: %@", error);
    });
}
- (void)toggleEditing {
    self.editing = !self.editing; self.window.editing = self.editing;
    [self apply];
    if (self.editing) [self.window makeKeyWindow]; else [self.game makeKeyWindow];
}
- (void)apply {
    NSUserDefaults *prefs = NSUserDefaults.standardUserDefaults;
    BOOL light = [prefs boolForKey:@"ZZZDamage.Light"], aliases = [prefs boolForKey:@"ZZZDamage.Aliases"];
    UIColor *text = light ? UIColor.blackColor : UIColor.whiteColor;
    CGFloat size = [prefs doubleForKey:@"ZZZDamage.Font"];
    size = isfinite(size) ? MAX(10, MIN(20, size)) : 13;
    CGFloat opacity = [prefs doubleForKey:@"ZZZDamage.Opacity"];
    opacity = isfinite(opacity) ? MAX(0.3, MIN(1, opacity)) : 0.86;
    NSMutableArray *history = [NSMutableArray arrayWithObject:[self action:@"Live session" block:^{ self.selected = nil; [self apply]; }]];
    for (NSDictionary *saved in self.history) [history addObject:[self action:[NSString stringWithFormat:@"%@ · %.0f raw", saved[@"saved_at"], [saved[@"total"] doubleValue]]
        block:^{ self.selected = saved; [self apply]; }]];
    NSMutableArray *widgets = [NSMutableArray array];
    for (NSUInteger i = 1; i < self.panels.count; i++) {
        VeritasPanel *panel = self.panels[i];
        [widgets addObject:[self setting:panel.title.text key:[panel.identifier stringByAppendingString:@".Hidden"] value:nil]];
    }
    NSArray *items = @[self.controls,
        [self action:self.editing ? @"Finish editing (⌃⌘E)" : @"Edit layout (⌃⌘E)" block:^{ [self toggleEditing]; }],
        [UIMenu menuWithTitle:@"Panels · checked means hidden" children:widgets],
        [UIMenu menuWithTitle:@"History" children:history],
        [UIMenu menuWithTitle:@"Appearance" children:@[
            [self setting:@"Light" key:@"ZZZDamage.Light" value:@YES], [self setting:@"Dark" key:@"ZZZDamage.Light" value:@NO],
            [self setting:@"Small text" key:@"ZZZDamage.Font" value:@11], [self setting:@"Medium text" key:@"ZZZDamage.Font" value:@13],
            [self setting:@"Large text" key:@"ZZZDamage.Font" value:@16],
            [self setting:@"Opacity 60%" key:@"ZZZDamage.Opacity" value:@0.6], [self setting:@"Opacity 85%" key:@"ZZZDamage.Opacity" value:@0.85],
            [self setting:@"Opacity 100%" key:@"ZZZDamage.Opacity" value:@1],
            [self setting:@"Streamer aliases" key:@"ZZZDamage.Aliases" value:nil]]],
        [UIMenu menuWithTitle:@"Export" children:@[
            [self action:@"Export JSON…" block:^{ [self share:NO]; }], [self action:@"Export CSV…" block:^{ [self share:YES]; }],
            [self setting:@"Autosave completed sessions" key:@"ZZZDamage.Autosave" value:nil]]],
        [self action:@"Reset layout" block:^{
            for (VeritasPanel *panel in self.panels) [prefs removeObjectForKey:panel.identifier];
            [self.window.rootViewController.view setNeedsLayout];
        }]];
    UIMenu *menu = [UIMenu menuWithTitle:@"ZZZ Damage" children:items];
    self.window.overrideUserInterfaceStyle = light ? UIUserInterfaceStyleLight : UIUserInterfaceStyleDark;
    for (VeritasPanel *panel in self.panels) {
        panel.editing = self.editing; panel.settings.menu = menu;
        panel.backgroundColor = light ? [UIColor colorWithWhite:0.96 alpha:opacity] : [UIColor colorWithWhite:0.055 alpha:opacity];
        panel.title.textColor = text; panel.title.font = [UIFont systemFontOfSize:size weight:UIFontWeightSemibold];
        panel.hidden = panel != self.panels.firstObject && [prefs boolForKey:[panel.identifier stringByAppendingString:@".Hidden"]];
    }
    self.metrics.textColor = text; self.metrics.font = [UIFont monospacedDigitSystemFontOfSize:size weight:UIFontWeightRegular];
    self.details.textColor = text; self.details.font = self.metrics.font;
    for (ZZZChart *chart in self.charts) { chart.textColor = text; chart.textSize = size; chart.aliases = aliases; }
    [self render];
}
- (void)render {
    NSDictionary *data = self.selected ?: self.live;
    double seconds = [data[@"seconds"] doubleValue], total = [data[@"total"] doubleValue];
    self.metrics.text = [NSString stringWithFormat:@"%@ · %@ hits\n%.0f raw DMG · %.1f game s\n%.1f raw DPS",
        self.selected ? @"Saved session" : [data[@"frozen"] boolValue] ? @"Result" : @"Live",
        data[@"hits"] ?: @0, total, seconds, seconds > 0 ? total / seconds : 0];
    NSMutableArray *lines = [NSMutableArray array];
    NSUInteger index = 0;
    BOOL aliases = [NSUserDefaults.standardUserDefaults boolForKey:@"ZZZDamage.Aliases"];
    for (NSDictionary *source in data[@"sources"]) {
        NSString *name = aliases ? [NSString stringWithFormat:@"Source %lu", (unsigned long)++index] : source[@"name"];
        [lines addObject:[NSString stringWithFormat:@"%@\n  %.0f raw · %.1f%% · %.1f raw/s", name,
            [source[@"damage"] doubleValue], total > 0 ? [source[@"damage"] doubleValue] / total * 100 : 0,
            seconds > 0 ? [source[@"damage"] doubleValue] / seconds : 0]];
    }
    self.details.text = [lines componentsJoinedByString:@"\n"];
    for (ZZZChart *chart in self.charts) chart.snapshot = data;
}
- (void)update:(NSDictionary *)snapshot game:(UIWindow *)game visible:(BOOL)visible {
    NSString *session = snapshot[@"session"];
    BOOL newSession = ![session isEqual:self.session];
    if (newSession) {
        [self archive]; self.archived = NO; self.selected = nil; self.session = session;
    }
    self.live = snapshot;
    BOOL newResult = [snapshot[@"frozen"] boolValue] && !self.archived;
    if (newResult) [self archive];
    self.game = game;
    if (self.window.windowScene != game.windowScene) {
        self.window.hidden = YES;
        self.window = [[ZZZDashboardWindow alloc] initWithWindowScene:game.windowScene];
        self.window.windowLevel = game.windowLevel + 1; self.window.editing = self.editing;
        VeritasOverlayLayout *layout = [VeritasOverlayLayout new]; self.window.rootViewController = layout;
        layout.view.backgroundColor = UIColor.clearColor;
        NSMutableArray *panels = [NSMutableArray array], *charts = [NSMutableArray array];
        NSArray *titles = @[@"Damage meter", @"Damage bars", @"Damage distribution", @"Damage timeline", @"All sources"];
        for (NSUInteger i = 0; i < titles.count; i++) {
            VeritasPanel *panel = [[VeritasPanel alloc] initWithTitle:titles[i] identifier:[NSString stringWithFormat:@"ZZZDamage.Panel%lu", (unsigned long)i]];
            [panels addObject:panel]; [layout.view addSubview:panel];
            if (i == 0) {
                self.metrics = [UILabel new]; self.metrics.numberOfLines = 0; [panel.stack addArrangedSubview:self.metrics];
            } else if (i == 4) {
                self.details = [UITextView new]; self.details.editable = NO; self.details.backgroundColor = UIColor.clearColor;
                [panel.stack addArrangedSubview:self.details];
            } else {
                ZZZChart *chart = [ZZZChart new]; chart.mode = i - 1; chart.backgroundColor = UIColor.clearColor;
                [charts addObject:chart]; [panel.stack addArrangedSubview:chart];
            }
        }
        self.panels = panels; self.charts = charts;
        __weak ZZZDashboard *weakSelf = self;
        layout.updatePanels = ^(CGRect bounds) {
            NSUInteger index = 0;
            for (VeritasPanel *panel in weakSelf.panels) {
                CGFloat width = MIN(340, bounds.size.width);
                CGFloat x = CGRectGetMaxX(bounds) - width - 12 - (index > 2 ? width + 12 : 0);
                CGFloat y = CGRectGetMinY(bounds) + 12 + (index > 2 ? index - 3 : index) * 235;
                [panel layoutWithin:bounds defaultFrame:CGRectMake(x, y, width, index == 0 ? 150 : 220)]; index++;
            }
        };
        [self apply];
    } else if (newResult || newSession) [self apply]; else [self render];
    self.window.hidden = !visible && !self.editing;
}
@end
