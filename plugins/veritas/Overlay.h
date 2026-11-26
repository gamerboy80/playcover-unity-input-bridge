#import "Export.h"
#import "Localization.h"
#import "Server.h"
#import "DamageCharts.h"
#import "OverlayControls.h"

@interface NSObject (VeritasKeyboardMonitor)
+ (id)addLocalMonitorForEventsMatchingMask:(NSUInteger)mask handler:(id (^)(id))handler;
- (NSUInteger)modifierFlags;
- (NSString *)charactersIgnoringModifiers;
- (BOOL)isARepeat;
@end
@interface VeritasOverlayWindow : VeritasPassthroughWindow
@end
@implementation VeritasOverlayWindow
@end

@interface VeritasOverlay : NSObject
@property(nonatomic, weak) UIWindow *gameWindow;
@property(nonatomic, strong) VeritasOverlayWindow *window;
@property(nonatomic, strong) VeritasBattle *battle;
@property(nonatomic, strong) VeritasServer *server;
@property(nonatomic) BOOL connected, shown, editing, inBattle;
@property(nonatomic, copy) NSArray<VeritasPanel *> *panels;
@property(nonatomic, strong) NSMutableDictionary<NSString *, UIView *> *widgets;
@property(nonatomic, strong) NSMutableArray<NSDictionary *> *history;
@property(nonatomic, strong) NSDictionary *selectedBattle;
@property(nonatomic, strong) UILabel *streamerBanner;
@property(nonatomic, strong) NSMutableArray<NSString *> *messages;
@property(nonatomic) BOOL renderPending;
@property(nonatomic, strong) UISegmentedControl *metricTabs;
@property(nonatomic, strong) UISegmentedControl *axisTabs;
- (void)render;
- (void)archiveBattle;
- (void)toggle;
- (void)toggleEditing;
@end
@implementation VeritasOverlay
- (instancetype)init {
    if ((self = [super init])) {
        _widgets = [NSMutableDictionary dictionary]; _history = [NSMutableArray array]; _messages = [NSMutableArray array];
        _server = [VeritasServer new];
        NSURL *documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
        NSData *data = [NSData dataWithContentsOfURL:[documents URLByAppendingPathComponent:@"Veritas/history.json"]];
        id history = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:NULL] : nil;
        if ([history isKindOfClass:NSArray.class]) for (id item in history) {
            if ([item isKindOfClass:NSDictionary.class] && [item[@"schema_version"] isEqual:@1] &&
                [item[@"avatars"] isKindOfClass:NSDictionary.class] && [item[@"turn_history"] isKindOfClass:NSArray.class]) [_history addObject:item];
        }
    }
    return self;
}
- (void)log:(NSString *)message {
    [self.messages addObject:message];
    if (self.messages.count > 200) [self.messages removeObjectAtIndex:0];
    NSLog(@"[Veritas] %@", message);
}
- (void)requestRender {
    if (self.renderPending) return;
    self.renderPending = YES;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC / 10), dispatch_get_main_queue(), ^{
        self.renderPending = NO; [self render];
    });
}
- (void)archiveBattle {
    [self.battle endTurn];
    if (!self.battle.turn && !self.battle.hits) return;
    NSMutableDictionary *snapshot = [self.battle.snapshot mutableCopy];
    snapshot[@"saved_at"] = [NSISO8601DateFormatter.new stringFromDate:NSDate.date];
    [self.history insertObject:snapshot atIndex:0];
    if (self.history.count > 50) [self.history removeLastObject];
    NSArray *history = [self.history copy];
    self.selectedBattle = nil;
    BOOL autosave = [NSUserDefaults.standardUserDefaults boolForKey:@"Veritas.AutoSave"];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
        NSURL *documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
        NSURL *directory = [documents URLByAppendingPathComponent:@"Veritas" isDirectory:YES];
        NSError *error = nil;
        BOOL ok = [NSFileManager.defaultManager createDirectoryAtURL:directory withIntermediateDirectories:YES attributes:nil error:&error];
        NSData *data = ok ? [NSJSONSerialization dataWithJSONObject:history options:0 error:&error] : nil;
        ok = data && [data writeToURL:[directory URLByAppendingPathComponent:@"history.json"] options:NSDataWritingAtomic error:&error];
        if (ok && autosave) ok = VeritasWriteExport(snapshot, NO, &error) && VeritasWriteExport(snapshot, YES, &error);
        if (!ok) dispatch_async(dispatch_get_main_queue(), ^{ [self log:error.localizedDescription ?: @"Could not save battle"]; });
    });
    [self applySettings];
}
- (void)updateVisibility {
    NSUserDefaults *prefs = NSUserDefaults.standardUserDefaults;
    BOOL show = self.editing || (self.shown && (![prefs boolForKey:@"Veritas.AutoHide"] || self.inBattle || self.selectedBattle));
    BOOL streamer = [prefs boolForKey:@"Veritas.Streamer"];
    self.window.hidden = !show && !streamer;
    self.streamerBanner.hidden = !streamer;
    for (VeritasPanel *panel in self.panels) panel.hidden = !show || (!(self.editing && panel == self.panels.firstObject) && ![prefs boolForKey:[panel.identifier stringByAppendingString:@".Visible"]]);
}
- (void)render {
    if (!self.window) return;
    VeritasBattle *battle = self.battle;
    NSMutableDictionary *series = [(self.selectedBattle ?: battle.series) mutableCopy];
    if (!self.selectedBattle) [series addEntriesFromDictionary:@{@"total_damage": @(battle.total), @"overkill_damage": @(battle.overkill),
        @"action_value": @(battle.actionValue), @"reset_action_value": @(battle.resetActionValue), @"turn_count": @(battle.turn), @"wave": @(battle.wave), @"cycle": @(battle.cycle),
        @"max_wave": @(battle.maxWave), @"max_cycle": @(battle.maxCycle), @"stage_id": @(battle.stage)}];
    NSDictionary *names = series[@"names"];
    if ([NSUserDefaults.standardUserDefaults boolForKey:@"Veritas.Streamer"]) {
        NSMutableDictionary *aliases = [NSMutableDictionary dictionary];
        for (NSString *key in [names.allKeys sortedArrayUsingSelector:@selector(compare:)]) aliases[key] = [NSString stringWithFormat:@"Character %lu", (unsigned long)aliases.count + 1];
        series[@"names"] = names = aliases;
    }
    for (UIView *widget in self.widgets.allValues) if ([widget isKindOfClass:VeritasDamageCharts.class]) ((VeritasDamageCharts *)widget).series = series;
    double total = [series[@"total_damage"] doubleValue], av = [series[@"action_value"] doubleValue];
    NSMutableArray *metrics = [NSMutableArray arrayWithArray:@[
        self.selectedBattle ? @"Saved battle" : self.inBattle ? @"● IN COMBAT" : @"Battle result",
        [NSString stringWithFormat:@"Total DMG    %@", VeritasNumber(total)],
        [NSString stringWithFormat:@"AV           %.2f (%.2f total)", MAX(0, av - [series[@"reset_action_value"] doubleValue]), av],
        [NSString stringWithFormat:@"DPAV         %.2f", av > 0 ? total / av : total],
        [NSString stringWithFormat:@"Overkill     %@", VeritasNumber([series[@"overkill_damage"] doubleValue])],
        [NSString stringWithFormat:@"Turn %@ · Wave %@/%@ · Cycles left %@/%@", series[@"turn_count"], series[@"wave"], series[@"max_wave"], series[@"cycle"], series[@"max_cycle"]],
        [NSString stringWithFormat:@"Stage %@", series[@"stage_id"]],
    ]];
    if (!self.connected) [metrics insertObject:@"Matching staged hooks are required" atIndex:0];
    NSDictionary *amounts = series[@"avatars"];
    NSMutableArray *legend = [NSMutableArray arrayWithObject:@"CHARACTER           DMG      DPAV"];
    for (NSString *key in [amounts.allKeys sortedArrayUsingSelector:@selector(compare:)]) {
        double damage = [amounts[key] doubleValue];
        [legend addObject:[NSString stringWithFormat:@"%@  %@  %.1f", names[key] ?: key, VeritasNumber(damage), av > 0 ? damage / av : damage]];
    }
    [self setLines:metrics kind:@"metrics"]; [self setLines:legend kind:@"legend"];
    NSMutableArray *skills = [NSMutableArray array];
    for (NSDictionary *skill in [series[@"skills"] reverseObjectEnumerator]) {
        if (skills.count >= 100) break;
        [skills addObject:[NSString stringWithFormat:@"T%@ · %@ · %@\n  %@ DMG · %.1f AV", skill[@"turn"], names[skill[@"owner"]] ?: skill[@"owner"], skill[@"skill"], VeritasNumber([skill[@"total_damage"] doubleValue]), [skill[@"action_value"] doubleValue]]];
    }
    [self setLines:skills kind:@"skills"];
    NSMutableArray *enemies = [NSMutableArray array], *stats = [NSMutableArray array];
    NSMutableAttributedString *enemyRows = [NSMutableAttributedString new];
    UIImage *hpIcon = VeritasCachedPortrait(@"properties/BaseHP");
    if (hpIcon) {
        NSTextAttachment *icon = [NSTextAttachment new]; icon.image = hpIcon; icon.bounds = CGRectMake(0, -4, 18, 18);
        [enemyRows appendAttributedString:[NSAttributedString attributedStringWithAttachment:icon]];
        [enemyRows appendAttributedString:[[NSAttributedString alloc] initWithString:@" HP\n"]];
    }
    UITextView *enemyView = (id)self.widgets[@"enemies"];
    NSDictionary *entities = series[@"entities"];
    for (NSString *key in [entities.allKeys sortedArrayUsingSelector:@selector(compare:)]) {
        NSDictionary *entity = entities[key], *properties = entity[@"stats"];
        BOOL player = [entity[@"entity"][@"team"] isEqual:@"Player"];
        if (!player && [series[@"enemy_formation_known"] boolValue] && ![series[@"enemy_formation"] containsObject:entity[@"entity"]]) continue;
        if (player) {
            NSString *uid = [entity[@"entity"][@"uid"] stringValue];
            [stats addObject:names[uid] ?: uid];
            NSNumber *delay = properties[@"ActionDelay"];
            if (delay) [stats addObject:[NSString stringWithFormat:@"  Next action: %.2f AV", av + MAX(0, delay.doubleValue)]];
            for (NSString *property in [properties.allKeys sortedArrayUsingSelector:@selector(compare:)]) [stats addObject:[NSString stringWithFormat:@"  %@: %.2f", property, [properties[property] doubleValue]]];
        } else {
            BOOL exclude = [NSUserDefaults.standardUserDefaults boolForKey:@"Veritas.DefenderExclusion"];
            if (exclude && [properties[@"CurrentHP"] doubleValue] <= 0) continue;
            NSString *hp = VeritasNumber([properties[@"CurrentHP"] doubleValue]);
            NSNumber *max = properties[@"MaxHP"];
            NSString *label = [NSString stringWithFormat:@"%@\n  HP %@ / %@  %@", entity[@"name"], hp, max ? VeritasNumber(max.doubleValue) : @"?",
                max.doubleValue > 0 ? [NSString stringWithFormat:@"%.0f%%", [properties[@"CurrentHP"] doubleValue] / max.doubleValue * 100] : @""];
            NSString *uid = [entity[@"entity"][@"uid"] stringValue];
            NSString *templateID = [series[@"enemies"][uid][@"id"] stringValue];
            UIImage *portrait = templateID ? VeritasPortrait(templateID, YES) : nil;
            if (portrait) {
                NSTextAttachment *attachment = [NSTextAttachment new]; attachment.image = portrait;
                attachment.bounds = CGRectMake(0, -8, 36, 36);
                [enemyRows appendAttributedString:[NSAttributedString attributedStringWithAttachment:attachment]];
            }
            [enemyRows appendAttributedString:[[NSAttributedString alloc] initWithString:[label stringByAppendingString:@"\n\n"] attributes:@{
                NSFontAttributeName: enemyView.font ?: [UIFont systemFontOfSize:13], NSForegroundColorAttributeName: enemyView.textColor ?: UIColor.whiteColor}]];
            [enemies addObject:label];
        }
    }
    if (enemyRows.length) {
        [enemyRows addAttributes:@{NSFontAttributeName: enemyView.font ?: [UIFont systemFontOfSize:13], NSForegroundColorAttributeName: enemyView.textColor ?: UIColor.whiteColor} range:NSMakeRange(0, enemyRows.length)];
        CGPoint offset = enemyView.contentOffset; enemyView.attributedText = enemyRows; [enemyView setContentOffset:offset animated:NO];
    } else [self setLines:enemies kind:@"enemies"];
    [self setLines:stats kind:@"stats"];
    [self setLines:[@[self.server.status ?: @"API stopped"] arrayByAddingObjectsFromArray:self.messages] kind:@"console"];
    [self updateVisibility];
}
- (void)setLines:(NSArray *)lines kind:(NSString *)kind {
    UITextView *view = (id)self.widgets[kind];
    NSString *text = lines.count ? [lines componentsJoinedByString:@"\n"] : @"Waiting for combat data";
    if (![text isEqual:view.text]) { CGPoint offset = view.contentOffset; view.text = text; [view setContentOffset:offset animated:NO]; }
}
- (UIAction *)action:(NSString *)title block:(void (^)(void))block {
    return [UIAction actionWithTitle:VeritasLocalized(title) image:nil identifier:nil handler:^(__unused UIAction *action) { block(); }];
}
- (UIAction *)setting:(NSString *)title key:(NSString *)key value:(id)value {
    NSUserDefaults *prefs = NSUserDefaults.standardUserDefaults;
    BOOL toggle = value == nil; id selected = value ?: @(![prefs boolForKey:key]);
    UIAction *action = [self action:title block:^{ [prefs setObject:selected forKey:key]; if ([key isEqual:@"Veritas.TextSize"]) [prefs removeObjectForKey:@"Veritas.CustomTextSize"]; [self applySettings]; }];
    action.state = (toggle ? [prefs boolForKey:key] : [[prefs objectForKey:key] isEqual:value]) ? UIMenuElementStateOn : UIMenuElementStateOff;
    return action;
}
- (void)prompt:(NSString *)title key:(NSString *)key {
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:title message:nil preferredStyle:UIAlertControllerStyleAlert];
    [alert addTextFieldWithConfigurationHandler:^(UITextField *field) { field.text = [NSUserDefaults.standardUserDefaults stringForKey:key]; }];
    [alert addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
    [alert addAction:[UIAlertAction actionWithTitle:@"Save" style:UIAlertActionStyleDefault handler:^(__unused UIAlertAction *action) {
        [NSUserDefaults.standardUserDefaults setObject:alert.textFields.firstObject.text ?: @"" forKey:key]; [self applySettings];
    }]];
    [self.window.rootViewController presentViewController:alert animated:YES completion:nil];
}
- (void)exportCSV:(BOOL)csv {
    NSDictionary *snapshot = self.selectedBattle ?: self.battle.snapshot;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
        NSError *error = nil; NSURL *url = VeritasWriteExport(snapshot, csv, &error);
        dispatch_async(dispatch_get_main_queue(), ^{
            if (!url) { [self log:error.localizedDescription ?: @"Export failed"]; [self render]; return; }
            if (!self.editing) { [self log:[@"Saved export: " stringByAppendingString:url.path]]; return; }
            UIActivityViewController *share = [[UIActivityViewController alloc] initWithActivityItems:@[url] applicationActivities:nil];
            share.popoverPresentationController.sourceView = self.panels.firstObject;
            [self.window.rootViewController presentViewController:share animated:YES completion:nil];
        });
    });
}
- (void)checkUpdates {
    BOOL beta = [NSUserDefaults.standardUserDefaults boolForKey:@"Veritas.Beta"];
    NSString *endpoint = beta ? @"https://api.github.com/repos/hessiser/veritas/releases?per_page=10" : @"https://api.github.com/repos/hessiser/veritas/releases/latest";
    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:[NSURL URLWithString:endpoint]];
    request.timeoutInterval = 15; [request setValue:@"Veritas-PlayCover" forHTTPHeaderField:@"User-Agent"];
    [[NSURLSession.sharedSession dataTaskWithRequest:request completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        id json = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:NULL] : nil;
        id release = [json isKindOfClass:NSArray.class] ? [json firstObject] : json;
        NSString *version = [release isKindOfClass:NSDictionary.class] ? release[@"tag_name"] : nil;
        BOOL success = !error && [(NSHTTPURLResponse *)response statusCode] == 200 && version.length;
        dispatch_async(dispatch_get_main_queue(), ^{
            [self log:success ? [NSString stringWithFormat:@"Upstream release %@. This native port is based on 0.2.58; upstream downloads target Windows. Update this repository and rebuild for PlayCover.", version] : error.localizedDescription ?: @"Could not check upstream releases"];
            [NSUserDefaults.standardUserDefaults setBool:YES forKey:@"Veritas.console.Visible"]; [self render];
        });
    }] resume];
}
- (void)changeMetric:(UISegmentedControl *)sender {
    [NSUserDefaults.standardUserDefaults setBool:sender.selectedSegmentIndex == 1 forKey:@"Veritas.DPAV"]; [self applySettings];
}
- (void)changeAxis:(UISegmentedControl *)sender {
    [NSUserDefaults.standardUserDefaults setBool:sender.selectedSegmentIndex == 1 forKey:@"Veritas.AVAxis"]; [self applySettings];
}
- (void)applySettings {
    NSUserDefaults *prefs = NSUserDefaults.standardUserDefaults;
    BOOL light = [prefs boolForKey:@"Veritas.Light"];
    self.window.overrideUserInterfaceStyle = light ? UIUserInterfaceStyleLight : UIUserInterfaceStyleDark;
    UIColor *text = light ? [UIColor colorWithWhite:0.1 alpha:1] : [UIColor colorWithWhite:0.92 alpha:1];
    CGFloat size = [prefs doubleForKey:@"Veritas.TextSize"], opacity = [prefs doubleForKey:@"Veritas.Opacity"];
    size = isfinite(size) ? MAX(8, MIN(48, size)) : 13;
    opacity = isfinite(opacity) ? MAX(0, MIN(1, opacity)) : 0.6;
    NSArray *themeNames = @[@"Egui", @"Indigo/jade", @"Grass/bronze", @"Warm", @"Cool", @"Seventies", @"Office Gray", @"Vermillion"];
    NSMutableArray *themes = [NSMutableArray array], *panels = [NSMutableArray array], *history = [NSMutableArray array];
    for (NSString *theme in themeNames) [themes addObject:[self setting:theme key:@"Veritas.Theme" value:theme]];
    for (VeritasPanel *panel in self.panels) [panels addObject:[self setting:panel.accessibilityLabel key:[panel.identifier stringByAppendingString:@".Visible"] value:nil]];
    [history addObject:[self action:@"Live battle" block:^{ self.selectedBattle = nil; [self applySettings]; }]];
    for (NSDictionary *snapshot in self.history) [history addObject:[self action:[NSString stringWithFormat:@"%@ · %@ DMG", snapshot[@"saved_at"] ?: @"Battle", VeritasNumber([snapshot[@"total_damage"] doubleValue])]
        block:^{ self.selectedBattle = snapshot; [self applySettings]; }]];
    NSMutableArray *owners = [NSMutableArray arrayWithObject:[self setting:@"Whole team" key:@"Veritas.BreakdownOwner" value:@""]];
    NSDictionary *names = (self.selectedBattle ?: self.battle.series)[@"names"];
    for (NSString *key in [names.allKeys sortedArrayUsingSelector:@selector(compare:)]) [owners addObject:[self setting:names[key] key:@"Veritas.BreakdownOwner" value:key]];
    NSMutableArray *languages = [NSMutableArray array];
    NSArray *languageNames = @[@"English", @"Français", @"Español", @"Deutsch", @"Italiano", @"日本語", @"Português", @"Nederlands", @"Русский", @"Tiếng Việt", @"中文", @"Polski"];
    NSArray *languageCodes = @[@"en", @"fr", @"es", @"de", @"it", @"ja", @"pt", @"nl", @"ru", @"vi", @"zh", @"pl"];
    for (NSUInteger index = 0; index < languageCodes.count; index++) [languages addObject:[self setting:languageNames[index] key:@"Veritas.Locale" value:languageCodes[index]]];
    NSArray *menus = @[
        [self action:@"Toggle overlay (⌘⇧D)" block:^{ [self toggle]; }],
        [self action:self.editing ? @"Finish editing (⌘⇧E)" : @"Edit layout (⌘⇧E)" block:^{ [self toggleEditing]; }],
        [UIMenu menuWithTitle:VeritasLocalized(@"Language") children:languages],
        [UIMenu menuWithTitle:@"Widgets" children:panels],
        [UIMenu menuWithTitle:@"Battle history" children:history],
        [UIMenu menuWithTitle:@"Charts" children:@[
            [self setting:@"DMG" key:@"Veritas.DPAV" value:@NO], [self setting:@"DPAV" key:@"Veritas.DPAV" value:@YES],
            [self setting:@"X axis: turns" key:@"Veritas.AVAxis" value:@NO], [self setting:@"X axis: AV" key:@"Veritas.AVAxis" value:@YES],
            [self setting:@"Breakdown: pie" key:@"Veritas.Pie" value:@YES], [self setting:@"Breakdown: bars" key:@"Veritas.Pie" value:@NO],
            [self setting:@"Show table" key:@"Veritas.Table" value:nil], [self setting:@"Show legend" key:@"Veritas.Legend" value:nil],
            [UIMenu menuWithTitle:@"Breakdown scope" children:owners]]],
        [UIMenu menuWithTitle:@"Appearance" children:@[
            [UIMenu menuWithTitle:@"Palette" children:themes],
            [self action:@"Custom accent (#RRGGBB)…" block:^{ [self prompt:@"Accent color, e.g. #36a2eb (empty uses theme)" key:@"Veritas.Accent"]; }],
            [self action:@"Heading size…" block:^{ [self prompt:@"Heading size, 8–48 points (empty follows body)" key:@"Veritas.HeadingSize"]; }],
            [UIMenu menuWithTitle:VeritasLocalized(@"Legend Text Style") children:@[[self setting:@"Body" key:@"Veritas.LegendStyle" value:@"Body"], [self setting:@"Heading" key:@"Veritas.LegendStyle" value:@"Heading"], [self setting:@"Small" key:@"Veritas.LegendStyle" value:@"Small"]]],
            [self action:@"Text size…" block:^{ [self prompt:@"Text size, 8–48 points" key:@"Veritas.CustomTextSize"]; }],
            [self action:@"Pie Chart Opacity" block:^{ [self prompt:@"Pie opacity, 0–1" key:@"Veritas.PieOpacity"]; }],
            [self setting:@"Dark" key:@"Veritas.Light" value:@NO], [self setting:@"Light" key:@"Veritas.Light" value:@YES],
            [self setting:@"Opacity 30%" key:@"Veritas.Opacity" value:@0.3], [self setting:@"Opacity 60%" key:@"Veritas.Opacity" value:@0.6],
            [self setting:@"Opacity 90%" key:@"Veritas.Opacity" value:@0.9],
            [self setting:@"Small text" key:@"Veritas.TextSize" value:@11], [self setting:@"Medium text" key:@"Veritas.TextSize" value:@13],
            [self setting:@"Large text" key:@"Veritas.TextSize" value:@16],
            [self setting:@"Hide outside battle" key:@"Veritas.AutoHide" value:nil],
            [self setting:@"Exclude defeated enemies" key:@"Veritas.DefenderExclusion" value:nil],
            [self setting:@"Streamer mode" key:@"Veritas.Streamer" value:nil],
            [self action:@"Streamer message…" block:^{ [self prompt:@"Streamer message" key:@"Veritas.StreamerMessage"]; }]]],
        [UIMenu menuWithTitle:@"Export" children:@[
            [self action:@"Export JSON…" block:^{ [self exportCSV:NO]; }], [self action:@"Export CSV…" block:^{ [self exportCSV:YES]; }],
            [self setting:@"Save JSON and CSV after battle" key:@"Veritas.AutoSave" value:nil],
            [self setting:@"Create date folders" key:@"Veritas.DateFolders" value:nil],
            [self action:@"Export folder…" block:^{ [self prompt:@"Export folder (empty uses Documents/Veritas/Exports)" key:@"Veritas.ExportPath"]; }]]],
        [self action:@"Reset current data" block:^{ NSArray *lineup = self.battle.series[@"lineup"]; [self.battle reset]; [self.battle setLineup:lineup]; self.selectedBattle = nil; [self render]; }],
        [self action:@"Reset layout" block:^{ for (VeritasPanel *panel in self.panels) [prefs removeObjectForKey:panel.identifier]; [self.window.rootViewController.view setNeedsLayout]; }],
        [self action:@"Help / shortcuts" block:^{ [self log:@"⌘⇧D: visibility · ⌘⇧E: edit/menu · Drag title / corner to move / resize. Gear: widgets, charts, history, export. Stats and attack categories use runtime enum names. Skill totals follow the owner's most recent manual skill, as upstream; delayed damage is not proof of a skill's causality."]; [prefs setBool:YES forKey:@"Veritas.console.Visible"]; [self render]; }],
        [self action:@"Check upstream release" block:^{ [self checkUpdates]; }],
        [self setting:@"Include upstream beta releases" key:@"Veritas.Beta" value:nil],
        [self action:@"About / updates" block:^{ [self log:@"Veritas PlayCover port · MIT © 2025 hessiser. Windows updater packages cannot update this native plugin. Rebuild with plugins/veritas/build.sh after pulling this repository."]; [prefs setBool:YES forKey:@"Veritas.console.Visible"]; [self render]; }],
    ];
    NSInteger theme = [themeNames indexOfObject:[prefs stringForKey:@"Veritas.Theme"]];
    UIColor *accent = VeritasCharacterColor(theme == NSNotFound ? 1 : (NSUInteger)theme);
    NSString *custom = [[prefs stringForKey:@"Veritas.Accent"] stringByReplacingOccurrencesOfString:@"#" withString:@""];
    unsigned rgb;
    NSScanner *scanner = [NSScanner scannerWithString:custom ?: @""];
    if (custom.length == 6 && [scanner scanHexInt:&rgb] && scanner.isAtEnd) accent = [UIColor colorWithRed:(rgb >> 16) / 255.0 green:((rgb >> 8) & 255) / 255.0 blue:(rgb & 255) / 255.0 alpha:1];
    double customSize = [[prefs stringForKey:@"Veritas.CustomTextSize"] doubleValue];
    if (isfinite(customSize) && customSize >= 8 && customSize <= 48) size = customSize;
    double headingSize = [[prefs stringForKey:@"Veritas.HeadingSize"] doubleValue];
    if (!isfinite(headingSize) || headingSize < 8 || headingSize > 48) headingSize = size;
    for (VeritasPanel *panel in self.panels) {
        panel.backgroundColor = light ? [UIColor colorWithWhite:0.96 alpha:opacity] : [UIColor colorWithWhite:0.055 alpha:opacity];
        panel.layer.borderColor = [accent colorWithAlphaComponent:0.6].CGColor;
        panel.layer.borderWidth = 0.5;
        panel.title.text = VeritasLocalized(panel.accessibilityLabel ?: panel.title.text);
        panel.title.textColor = text; panel.title.font = [UIFont systemFontOfSize:headingSize weight:UIFontWeightSemibold];
        panel.settings.tintColor = accent; panel.resize.tintColor = accent;
        panel.settings.menu = [UIMenu menuWithTitle:@"Veritas" children:menus];
    }
    for (UIView *widget in self.widgets.allValues) {
        if ([widget isKindOfClass:VeritasDamageCharts.class]) {
            VeritasDamageCharts *chart = (id)widget;
            chart.textColor = text; chart.textSize = size; chart.dpav = [prefs boolForKey:@"Veritas.DPAV"];
            chart.avAxis = [prefs boolForKey:@"Veritas.AVAxis"]; chart.pie = [prefs boolForKey:@"Veritas.Pie"];
            double pieOpacity = [prefs objectForKey:@"Veritas.PieOpacity"] ? [prefs doubleForKey:@"Veritas.PieOpacity"] : 0.8;
            chart.pieOpacity = isfinite(pieOpacity) ? MAX(0, MIN(1, pieOpacity)) : 0.8;
            chart.showLegend = [prefs boolForKey:@"Veritas.Legend"]; chart.showTable = [prefs boolForKey:@"Veritas.Table"];
            NSString *selected = [prefs stringForKey:@"Veritas.BreakdownOwner"]; chart.selectedOwner = selected.length ? selected : nil;
        } else if ([widget isKindOfClass:UITextView.class]) {
            ((UITextView *)widget).textColor = text;
            ((UITextView *)widget).font = [UIFont monospacedDigitSystemFontOfSize:size weight:UIFontWeightRegular];
        }
    }
    NSString *legendStyle = [prefs stringForKey:@"Veritas.LegendStyle"];
    CGFloat legendSize = [legendStyle isEqual:@"Heading"] ? headingSize : [legendStyle isEqual:@"Small"] ? MAX(8, size - 2) : size;
    ((UITextView *)self.widgets[@"legend"]).font = [UIFont monospacedDigitSystemFontOfSize:legendSize weight:UIFontWeightRegular];
    self.metricTabs.selectedSegmentIndex = [prefs boolForKey:@"Veritas.DPAV"] ? 1 : 0;
    self.axisTabs.selectedSegmentIndex = [prefs boolForKey:@"Veritas.AVAxis"] ? 1 : 0;
    self.metricTabs.tintColor = accent; self.axisTabs.tintColor = accent;
    self.streamerBanner.text = [prefs stringForKey:@"Veritas.StreamerMessage"] ?: @"Veritas";
    [self render];
}
- (void)attachToWindow:(UIWindow *)gameWindow {
    UIWindowScene *scene = gameWindow.windowScene;
    if (!scene || [gameWindow isKindOfClass:VeritasOverlayWindow.class]) return;
    self.gameWindow = gameWindow;
    if (self.window.windowScene == scene) return;
    self.window.hidden = YES;
    self.window = [[VeritasOverlayWindow alloc] initWithWindowScene:scene];
    self.window.windowLevel = MAX(UIWindowLevelNormal, gameWindow.windowLevel) + 1;
    VeritasOverlayLayout *controller = [VeritasOverlayLayout new]; self.window.rootViewController = controller;
    UIView *root = controller.view; root.backgroundColor = UIColor.clearColor;
    self.streamerBanner = [UILabel new]; self.streamerBanner.backgroundColor = UIColor.blackColor;
    self.streamerBanner.textColor = UIColor.whiteColor; self.streamerBanner.font = [UIFont systemFontOfSize:12 weight:UIFontWeightSemibold];
    self.streamerBanner.translatesAutoresizingMaskIntoConstraints = NO; [root addSubview:self.streamerBanner];
    [NSLayoutConstraint activateConstraints:@[[self.streamerBanner.leadingAnchor constraintEqualToAnchor:root.leadingAnchor],
        [self.streamerBanner.bottomAnchor constraintEqualToAnchor:root.bottomAnchor], [self.streamerBanner.widthAnchor constraintEqualToConstant:260],
        [self.streamerBanner.heightAnchor constraintEqualToConstant:28]]];
    NSArray *definitions = @[@[@"Character Damage", @"characters"], @[@"Battle Metrics", @"metrics"], @[@"Damage Distribution", @"distribution"],
        @[@"Damage Bars", @"bars"], @[@"Character Legend", @"legend"], @[@"Damage Type Breakdown", @"types"],
        @[@"Real-Time Damage", @"graph"], @[@"Enemy Stats", @"enemies"],
        @[@"Character Stats", @"stats"], @[@"Skill History", @"skills"], @[@"Console", @"console"]];
    NSMutableArray *panels = [NSMutableArray array];
    for (NSArray *definition in definitions) {
        NSString *title = definition[0], *kind = definition[1];
        VeritasPanel *panel = [[VeritasPanel alloc] initWithTitle:title identifier:[@"Veritas." stringByAppendingString:kind]];
        panel.accessibilityLabel = title;
        [panels addObject:panel]; [root addSubview:panel];
        if ([kind isEqual:@"characters"] || [kind isEqual:@"graph"]) {
            BOOL metric = [kind isEqual:@"characters"];
            UISegmentedControl *tabs = [[UISegmentedControl alloc] initWithItems:metric ? @[@"DMG", @"DPAV"] : @[VeritasLocalized(@"Turn"), @"AV"]];
            [tabs addTarget:self action:metric ? @selector(changeMetric:) : @selector(changeAxis:) forControlEvents:UIControlEventValueChanged];
            [panel.stack addArrangedSubview:tabs];
            if (metric) self.metricTabs = tabs; else self.axisTabs = tabs;
        }
        UIView *widget;
        if ([@[@"characters", @"distribution", @"bars", @"types", @"graph"] containsObject:kind]) {
            VeritasDamageCharts *chart = [VeritasDamageCharts new]; chart.kind = kind; chart.opaque = NO; widget = chart;
        } else {
            UITextView *rows = [UITextView new]; rows.editable = NO; rows.selectable = NO;
            rows.textContainerInset = UIEdgeInsetsZero; rows.textContainer.lineFragmentPadding = 0; widget = rows;
        }
        widget.backgroundColor = UIColor.clearColor;
        self.widgets[kind] = widget; [panel.stack addArrangedSubview:widget];

    }
    self.panels = panels;
    __weak VeritasOverlay *weakSelf = self;
    controller.updatePanels = ^(CGRect bounds) {
        NSUInteger index = 0;
        for (VeritasPanel *panel in weakSelf.panels) {
            NSUInteger column = index < 2 ? 0 : 1 + (index - 2) % 2, row = index < 2 ? index : (index - 2) / 2;
            CGFloat width = MIN(300, MAX(220, (bounds.size.width - 48) / 3));
            CGFloat height = index == 0 ? 250 : 215;
            [panel layoutWithin:bounds defaultFrame:CGRectMake(CGRectGetMaxX(bounds) - (column + 1) * (width + 10),
                CGRectGetMinY(bounds) + 12 + row * 265, width, height)]; index++;
        }
    };
    self.window.editing = self.editing;
    for (VeritasPanel *panel in self.panels) panel.editing = self.editing;
    [self applySettings];
}
- (void)toggle { self.shown = !self.shown; [NSUserDefaults.standardUserDefaults setBool:self.shown forKey:@"Veritas.Shown"]; [self updateVisibility]; }
- (void)toggleEditing {
    self.editing = !self.editing; self.window.editing = self.editing;
    for (VeritasPanel *panel in self.panels) panel.editing = self.editing;
    [self applySettings];
    if (self.editing) [self.window makeKeyWindow];
    else { [self.window.rootViewController dismissViewControllerAnimated:NO completion:nil]; [self.gameWindow makeKeyWindow]; }
}
@end
