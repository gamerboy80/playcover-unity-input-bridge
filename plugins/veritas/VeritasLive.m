#import <UIKit/UIKit.h>
#import <mach-o/dyld.h>
#include <stdatomic.h>
#include <string.h>
#import "Telemetry.h"
#import "VeritasProfile.h"

#import "DamageCharts.h"
#import "OverlayControls.h"

@interface NSObject (VeritasKeyboardMonitor)
+ (id)addLocalMonitorForEventsMatchingMask:(NSUInteger)mask handler:(id (^)(id))handler;
- (NSUInteger)modifierFlags;
- (NSString *)charactersIgnoringModifiers;
- (BOOL)isARepeat;
@end

// The charts are read only. Let pointer events reach the game.
@interface VeritasOverlayWindow : UIWindow
@property(nonatomic) BOOL editing;
@end
@implementation VeritasOverlayWindow
- (UIView *)hitTest:(CGPoint)point withEvent:(UIEvent *)event {
    if (!self.editing) return nil;
    UIView *hit = [super hitTest:point withEvent:event];
    for (UIView *ancestor = hit; ancestor; ancestor = ancestor.superview) {
        if ([ancestor isKindOfClass:VeritasPanel.class]) return hit;
    }
    return nil;
}
@end

@interface VeritasOverlay : NSObject
@property(nonatomic, weak) UIWindow *gameWindow;
@property(nonatomic, strong) VeritasOverlayWindow *window;
@property(nonatomic, strong) UILabel *summary;
@property(nonatomic, strong) VeritasDamageCharts *charts;
@property(nonatomic, strong) VeritasBattle *battle;
@property(nonatomic) BOOL connected;
@property(nonatomic) BOOL shown;
@property(nonatomic) BOOL editing;
@property(nonatomic) BOOL inBattle;
@property(nonatomic, copy) NSArray<VeritasPanel *> *panels;
@property(nonatomic, strong) UITextView *attackRows;
@property(nonatomic, strong) UITextView *skillRows;
@property(nonatomic, strong) UILabel *streamerBanner;
@end

static NSString * const VeritasLightKey = @"Veritas.Light";
static NSString * const VeritasOpacityKey = @"Veritas.Opacity";
static NSString * const VeritasTextSizeKey = @"Veritas.TextSize";
static NSString * const VeritasAutoHideKey = @"Veritas.AutoHide";
static NSString * const VeritasStreamerKey = @"Veritas.Streamer";
static NSString * const VeritasAttackPanelKey = @"Veritas.ShowAttackTypes";
static NSString * const VeritasSkillPanelKey = @"Veritas.ShowSkills";

@implementation VeritasOverlay
- (void)updateVisibility {
    NSUserDefaults *prefs = NSUserDefaults.standardUserDefaults;
    BOOL autoHide = [prefs boolForKey:VeritasAutoHideKey];
    BOOL showPanels = self.editing || (self.shown && (!autoHide || self.inBattle));
    BOOL streamer = [prefs boolForKey:VeritasStreamerKey];
    self.window.hidden = !showPanels && !streamer;
    self.streamerBanner.hidden = !streamer;
    self.panels[0].hidden = !showPanels;
    self.panels[1].hidden = !showPanels || (!self.editing && ![prefs boolForKey:VeritasAttackPanelKey]);
    self.panels[2].hidden = !showPanels || (!self.editing && ![prefs boolForKey:VeritasSkillPanelKey]);
}

- (void)render {
    VeritasBattle *battle = self.battle;
    if (!self.connected) {
        self.summary.text = @"Live capture requires the matching HSR preview build.";
    } else if (!battle.hits) {
        self.summary.text = @"Waiting for player damage…";
    } else {
        NSMutableArray<NSString *> *details = [NSMutableArray array];
        if (battle.wave) [details addObject:[NSString stringWithFormat:@"Wave %u", battle.wave]];
        if (battle.turn) [details addObject:[NSString stringWithFormat:@"Turn %u", battle.turn]];
        if (battle.actionValue > 0) {
            [details addObject:[NSString stringWithFormat:@"%.1f damage/AV", battle.total / battle.actionValue]];
        }
        NSString *damage = [NSNumberFormatter localizedStringFromNumber:@(llround(battle.total)) numberStyle:NSNumberFormatterDecimalStyle];
        NSString *overkill = [NSNumberFormatter localizedStringFromNumber:@(llround(battle.overkill)) numberStyle:NSNumberFormatterDecimalStyle];
        self.summary.text = [NSString stringWithFormat:@"%@ damage  ·  %lu %@\n%@%@",
            damage, (unsigned long)battle.hits, battle.hits == 1 ? @"hit" : @"hits",
            [details componentsJoinedByString:@"  ·  "],
            battle.overkill > 0 ? [NSString stringWithFormat:@"\n%@ overkill", overkill] : @""];
    }
    NSDictionary *series = battle.series;
    NSDictionary *names = series[@"names"];
    if ([NSUserDefaults.standardUserDefaults boolForKey:VeritasStreamerKey]) {
        NSMutableDictionary *aliases = [NSMutableDictionary dictionary];
        NSMutableSet *owners = [NSMutableSet setWithArray:[series[@"avatars"] allKeys]];
        [owners addObjectsFromArray:[series[@"skills"] valueForKey:@"owner"]];
        for (NSString *key in [[owners allObjects] sortedArrayUsingSelector:@selector(compare:)]) {
            aliases[key] = [NSString stringWithFormat:@"Character %lu", (unsigned long)aliases.count + 1];
        }
        names = aliases;
        NSMutableDictionary *privateSeries = [series mutableCopy];
        privateSeries[@"names"] = names;
        series = privateSeries;
    }
    self.charts.series = series;
    self.charts.hidden = battle.hits == 0;

    NSDictionary<NSString *, NSDictionary<NSString *, NSNumber *> *> *attackDamage = series[@"attackDamage"];
    NSMutableArray *attackLines = [NSMutableArray array];
    for (NSString *key in [[attackDamage allKeys] sortedArrayUsingSelector:@selector(compare:)]) {
        [attackLines addObject:names[key] ?: key];
        NSDictionary<NSString *, NSNumber *> *totals = attackDamage[key];
        for (NSString *label in [totals keysSortedByValueUsingSelector:@selector(compare:)].reverseObjectEnumerator) {
            NSString *amount = [NSNumberFormatter localizedStringFromNumber:@(llround(totals[label].doubleValue))
                                                                 numberStyle:NSNumberFormatterDecimalStyle];
            [attackLines addObject:[NSString stringWithFormat:@"  %@  %@", label, amount]];
        }
    }
    if (battle.unattributedDirectLoss > 0) {
        NSString *amount = [NSNumberFormatter localizedStringFromNumber:@(llround(battle.unattributedDirectLoss))
                                                             numberStyle:NSNumberFormatterDecimalStyle];
        [attackLines addObject:[NSString stringWithFormat:@"Unattributed direct HP loss  %@", amount]];
    }
    [self setLines:attackLines inRows:self.attackRows placeholder:@"Waiting for damage…"];
    NSMutableArray *skillLines = [NSMutableArray array];
    for (NSDictionary *use in [series[@"skills"] reverseObjectEnumerator]) {
        NSString *owner = names[use[@"owner"]] ?: use[@"owner"];
        NSNumber *turn = use[@"turn"];
        [skillLines addObject:[NSString stringWithFormat:@"Turn %@ · %@ · %@", turn, owner, use[@"skill"]]];
    }
    [self setLines:skillLines inRows:self.skillRows placeholder:@"Waiting for a skill…"];
    [self updateVisibility];
}

- (void)setLines:(NSArray<NSString *> *)lines inRows:(UITextView *)rows placeholder:(NSString *)placeholder {
    NSString *text = lines.count ? [lines componentsJoinedByString:@"\n"] : placeholder;
    if ([text isEqualToString:rows.text]) return;
    CGPoint offset = rows.contentOffset;
    rows.text = text;
    if (self.editing) [rows setContentOffset:offset animated:NO];
}

- (UIAction *)setting:(NSString *)title key:(NSString *)key value:(id)value {
    NSUserDefaults *prefs = NSUserDefaults.standardUserDefaults;
    id previous = [prefs objectForKey:key];
    BOOL toggle = value == nil;
    if (toggle) value = @(![prefs boolForKey:key]);
    __weak VeritasOverlay *weakSelf = self;
    UIAction *action = [UIAction actionWithTitle:title image:nil identifier:nil handler:^(__unused UIAction *selected) {
        [prefs setObject:value forKey:key];
        [weakSelf applySettings];
    }];
    BOOL on = toggle ? [previous boolValue] : [previous isEqual:value];
    action.state = on ? UIMenuElementStateOn : UIMenuElementStateOff;
    return action;
}

- (void)applySettings {
    NSUserDefaults *prefs = NSUserDefaults.standardUserDefaults;
    BOOL light = [prefs boolForKey:VeritasLightKey];
    CGFloat opacity = [prefs doubleForKey:VeritasOpacityKey];
    CGFloat size = [prefs doubleForKey:VeritasTextSizeKey];
    UIColor *text = light ? UIColor.blackColor : UIColor.whiteColor;
    UIColor *background = light ? [UIColor colorWithWhite:0.94 alpha:opacity] :
        [UIColor colorWithRed:0.05 green:0.07 blue:0.12 alpha:opacity];
    __weak VeritasOverlay *weakSelf = self;
    UIAction *reset = [UIAction actionWithTitle:@"Reset panel positions and sizes" image:nil identifier:nil
        handler:^(__unused UIAction *action) {
            for (VeritasPanel *panel in weakSelf.panels) [prefs removeObjectForKey:panel.identifier];
            [weakSelf.window.rootViewController.view setNeedsLayout];
        }];
    NSArray *menus = @[
        [UIMenu menuWithTitle:@"Theme" children:@[
            [self setting:@"Dark" key:VeritasLightKey value:@NO],
            [self setting:@"Light" key:VeritasLightKey value:@YES]]],
        [UIMenu menuWithTitle:@"Opacity" children:@[
            [self setting:@"60%" key:VeritasOpacityKey value:@0.6],
            [self setting:@"80%" key:VeritasOpacityKey value:@0.8],
            [self setting:@"100%" key:VeritasOpacityKey value:@1.0]]],
        [UIMenu menuWithTitle:@"Text size" children:@[
            [self setting:@"Small" key:VeritasTextSizeKey value:@11],
            [self setting:@"Medium" key:VeritasTextSizeKey value:@13],
            [self setting:@"Large" key:VeritasTextSizeKey value:@16]]],
        [self setting:@"Hide outside battle" key:VeritasAutoHideKey value:nil],
        [self setting:@"Streamer mode" key:VeritasStreamerKey value:nil],
        [self setting:@"Show attack types" key:VeritasAttackPanelKey value:nil],
        [self setting:@"Show skill history" key:VeritasSkillPanelKey value:nil],
        reset,
    ];
    self.summary.textColor = text;
    self.summary.font = [UIFont monospacedDigitSystemFontOfSize:size weight:UIFontWeightRegular];
    self.charts.textColor = text;
    self.charts.textSize = size;
    for (UITextView *rows in @[self.attackRows, self.skillRows]) {
        rows.textColor = text;
        rows.font = [UIFont monospacedDigitSystemFontOfSize:size weight:UIFontWeightRegular];
    }
    for (VeritasPanel *panel in self.panels) {
        panel.backgroundColor = background;
        panel.title.textColor = text;
        panel.title.font = [UIFont boldSystemFontOfSize:size + 3];
        panel.settings.menu = [UIMenu menuWithTitle:@"Veritas" children:menus];
    }
    [self render];
}

- (UITextView *)newRowsForPanel:(VeritasPanel *)panel {
    UITextView *rows = [UITextView new];
    rows.backgroundColor = UIColor.clearColor;
    rows.editable = NO;
    rows.selectable = NO;
    rows.textContainerInset = UIEdgeInsetsZero;
    rows.textContainer.lineFragmentPadding = 0;
    [panel.stack addArrangedSubview:rows];
    [rows.heightAnchor constraintEqualToAnchor:panel.heightAnchor constant:-60].active = YES;
    return rows;
}

- (void)attachToWindow:(UIWindow *)gameWindow {
    UIWindowScene *scene = gameWindow.windowScene;
    if (!scene || [gameWindow isKindOfClass:VeritasOverlayWindow.class]) return;
    self.gameWindow = gameWindow;
    if (self.window.windowScene == scene) return;
    self.window.hidden = YES;
    VeritasOverlayWindow *window = [[VeritasOverlayWindow alloc] initWithWindowScene:scene];
    window.windowLevel = MAX(UIWindowLevelNormal, gameWindow.windowLevel) + 1;
    VeritasOverlayLayout *controller = [VeritasOverlayLayout new];
    window.rootViewController = controller;
    UIView *root = controller.view;
    root.backgroundColor = UIColor.clearColor;
    self.window = window;

    self.streamerBanner = [UILabel new];
    self.streamerBanner.text = @"  Veritas";
    self.streamerBanner.font = [UIFont boldSystemFontOfSize:12];
    self.streamerBanner.backgroundColor = UIColor.blackColor;
    self.streamerBanner.textColor = UIColor.whiteColor;
    self.streamerBanner.translatesAutoresizingMaskIntoConstraints = NO;
    [root addSubview:self.streamerBanner];
    [NSLayoutConstraint activateConstraints:@[
        [self.streamerBanner.leadingAnchor constraintEqualToAnchor:root.leadingAnchor],
        [self.streamerBanner.trailingAnchor constraintEqualToAnchor:root.trailingAnchor],
        [self.streamerBanner.bottomAnchor constraintEqualToAnchor:root.bottomAnchor],
        [self.streamerBanner.heightAnchor constraintEqualToConstant:28],
    ]];
    VeritasPanel *overview = [[VeritasPanel alloc] initWithTitle:@"Battle damage" identifier:@"Veritas.OverviewFrame"];
    VeritasPanel *types = [[VeritasPanel alloc] initWithTitle:@"Damage by attack type" identifier:@"Veritas.TypesFrame"];
    VeritasPanel *skills = [[VeritasPanel alloc] initWithTitle:@"Skill history" identifier:@"Veritas.SkillsFrame"];
    self.panels = @[overview, types, skills];
    for (VeritasPanel *panel in self.panels) [root addSubview:panel];
    self.summary = [UILabel new];
    self.summary.numberOfLines = 0;
    self.charts = [VeritasDamageCharts new];
    self.charts.opaque = NO;
    self.charts.backgroundColor = UIColor.clearColor;
    [overview.stack addArrangedSubview:self.summary];
    [overview.stack addArrangedSubview:self.charts];
    [self.summary setContentCompressionResistancePriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisVertical];
    NSLayoutConstraint *chartHeight = [self.charts.heightAnchor constraintEqualToConstant:364];
    chartHeight.priority = UILayoutPriorityDefaultHigh;
    chartHeight.active = YES;
    self.attackRows = [self newRowsForPanel:types];
    self.skillRows = [self newRowsForPanel:skills];
    __weak UIView *weakRoot = root;
    controller.updatePanels = ^(CGRect bounds) {
        if (!weakRoot || CGRectIsEmpty(bounds)) return;
        CGFloat y = CGRectGetMinY(bounds) + 12;
        CGFloat width = MIN(320, MAX(200, (bounds.size.width - 36) * 0.5));
        CGFloat right = CGRectGetMaxX(bounds) - width - 12;
        CGFloat left = MAX(CGRectGetMinX(bounds), right - width - 12);
        [overview layoutWithin:bounds defaultFrame:CGRectMake(right, y, width, 475)];
        [types layoutWithin:bounds defaultFrame:CGRectMake(left, y, width, 260)];
        [skills layoutWithin:bounds defaultFrame:CGRectMake(left, y + 272, width, 203)];
    };
    window.editing = self.editing;
    for (VeritasPanel *panel in self.panels) panel.editing = self.editing;
    [self applySettings];
}

- (void)toggle {
    self.shown = !self.shown;
    [self updateVisibility];
}

- (void)toggleEditing {
    self.editing = !self.editing;
    self.window.editing = self.editing;
    for (VeritasPanel *panel in self.panels) panel.editing = self.editing;
    [self updateVisibility];
}

@end

typedef uintptr_t (*DamageRoutine)(void *, void *, const void *, void *, void *,
                                   void *, void *, void *, bool, void *);
typedef void (*BattleRoutine)(void *, void *);

static uintptr_t unity;
static VeritasOverlay *overlay;
static _Atomic(unsigned) activeBattle;
static _Atomic(unsigned) nextBattle;
static unsigned displayedBattle;
static _Thread_local unsigned damageDepth;

static void BattleBegin(void *mode, void *method) {
    const unsigned id = ++nextBattle;
    atomic_store(&activeBattle, id);
    dispatch_async(dispatch_get_main_queue(), ^{
        displayedBattle = id;
        overlay.inBattle = YES;
        [overlay.battle reset];
        [overlay render];
    });
    ((BattleRoutine)(unity + VeritasBattleBeginOriginal))(mode, method);
}

static void BattleEnd(void *mode, void *method) {
    ((BattleRoutine)(unity + VeritasBattleEndOriginal))(mode, method);
    unsigned finished = atomic_exchange(&activeBattle, 0);
    dispatch_async(dispatch_get_main_queue(), ^{
        if (displayedBattle != finished) return;
        overlay.inBattle = NO;
        [overlay render];
    });
}

static void TurnBegin(void *mode, void *method) {
    unsigned battle = atomic_load(&activeBattle);
    ((BattleRoutine)(unity + VeritasTurnBeginOriginal))(mode, method);
    if (!battle || atomic_load(&activeBattle) != battle) return;
    int64_t (*elapsed)(void *) = (void *)(unity + VeritasGetElapsedActionDelay);
    unsigned (*waveNumber)(void *) = (void *)(unity + VeritasGetWave);
    double actionValue = VeritasFixPoint(elapsed(mode)) * 10;
    unsigned wave = waveNumber(mode);
    dispatch_async(dispatch_get_main_queue(), ^{
        if (displayedBattle != battle) return;
        [overlay.battle beginTurnAtActionValue:actionValue wave:wave];
        [overlay render];
    });
}

static uint32_t AvatarID(void *attacker) {
    uint32_t (*idForEntity)(void *) = (void *)(unity + VeritasGetAvatarID);
    void *(*actualOwner)(void *) = (void *)(unity + VeritasGetActualOwner);
    void *owner = actualOwner(attacker);
    uint32_t avatar = idForEntity(owner ?: attacker);
    if (avatar) return avatar;

    void *(*ownerWorld)(void *) = (void *)(unity + VeritasGetOwnerWorld);
    void *(*entityManager)(void *) = (void *)(unity + VeritasGetEntityManager);
    void *(*summoner)(void *, void *) = (void *)(unity + VeritasGetEntitySummoner);
    void *world = ownerWorld(attacker);
    void *manager = world ? entityManager(world) : NULL;
    return manager ? idForEntity(summoner(manager, attacker)) : 0;
}

static NSString *GameString(const char *string) {
    if (!string) return nil;
    int32_t length;
    memcpy(&length, string + 16, sizeof(length));
    if (length <= 0 || length > 256) return nil;
    NSString *name = [[NSString alloc] initWithCharacters:(const unichar *)(string + 20) length:(NSUInteger)length];
    return [[name stringByReplacingOccurrencesOfString:@"<ub>" withString:@""]
        stringByReplacingOccurrencesOfString:@"</ub>" withString:@""];
}

static NSString *AvatarName(uint32_t avatar) {
    const char *(*avatarName)(uint32_t) = (void *)(unity + VeritasGetAvatarName);
    return avatar ? GameString(avatarName(avatar)) : nil;
}

static NSString *SkillName(void *component, int index, int variant) {
    void *(*skillData)(void *, int, int) = (void *)(unity + VeritasGetSkillData);
    void *skill = skillData(component, index, variant);
    if (!skill) return nil;
    void *row;
    memcpy(&row, (const char *)skill + VeritasSkillRowField, sizeof(row));
    if (!row) return nil;
    void *(*objectType)(void *) = (void *)(unity + VeritasGetObjectType);
    const char *(*typeName)(void *) = (void *)(unity + VeritasGetTypeName);
    void *type = objectType(row);
    NSString *name = type ? GameString(typeName(type)) : nil;
    uintptr_t getter = 0;
    if ([name isEqualToString:@"AvatarSkillRowData"]) getter = VeritasGetAvatarSkillName;
    else if ([name isEqualToString:@"ServantSkillRowData"]) getter = VeritasGetServantSkillName;
    else if ([name isEqualToString:@"MonsterSkillRowData"]) getter = VeritasGetMonsterSkillName;
    else if ([name isEqualToString:@"BattleEventSkillRowData"]) getter = VeritasGetBattleEventSkillName;
    if (!getter) return nil;
    typedef struct { int32_t hash; uint64_t hash64; } TextID;
    TextID (*getName)(void *) = (void *)(unity + getter);
    const char *(*getText)(TextID, void *) = (void *)(unity + VeritasGetText);
    return GameString(getText(getName(row), NULL));
}

static bool UseSkill(void *component, int index, void *cursor, bool alternate,
                     void *floats, void *strings, int variant, void *method) {
    typedef bool (*Routine)(void *, int, void *, bool, void *, void *, int, void *);
    unsigned battle = atomic_load(&activeBattle);
    bool used = ((Routine)(unity + VeritasUseSkillOriginal))(component, index, cursor, alternate,
                                                            floats, strings, variant, method);
    if (!used || !battle || atomic_load(&activeBattle) != battle) return used;
    void *(*owner)(void *) = (void *)(unity + VeritasGetComponentOwner);
    int (*team)(void *) = (void *)(unity + VeritasGetTeam);
    void *entity = owner(component);
    if (!entity || team(entity) != 1) return used;
    @autoreleasepool {
        NSString *skill = SkillName(component, index, variant);
        if (!skill.length) skill = [NSString stringWithFormat:@"Skill slot %d", index + 1];
        uint32_t avatar = AvatarID(entity);
        uint32_t (*runtimeOwner)(void *) = (void *)(unity + VeritasGetActualOwnerID);
        uint32_t identifier = avatar ?: runtimeOwner(entity);
        NSString *name = AvatarName(avatar);
        dispatch_async(dispatch_get_main_queue(), ^{
            if (displayedBattle != battle) return;
            [overlay.battle recordSkill:skill owner:identifier name:name];
            [overlay render];
        });
    }
    return used;
}

static uintptr_t Damage(void *context, void *specification, const void *info,
                        void *attackerAbility, void *defenderAbility, void *attacker,
                        void *defender, void *singleTarget, bool flag, void *method) {
    unsigned battle = atomic_load(&activeBattle);
    int (*team)(void *) = (void *)(unity + VeritasGetTeam);
    uint32_t (*ownerID)(void *) = (void *)(unity + VeritasGetActualOwnerID);
    int64_t (*property)(void *, int) = (void *)(unity + VeritasGetProperty);
    bool track = battle && info && attacker && defender && defenderAbility &&
                 team(attacker) == 1 && team(defender) != 1;
    uint32_t owner = track ? ownerID(attacker) : 0;
    double before = owner ? VeritasFixPoint(property(defenderAbility, 1)) : 0;
    damageDepth++;
    uintptr_t result = ((DamageRoutine)(unity + VeritasDamageOriginal))(
        context, specification, info, attackerAbility, defenderAbility,
        attacker, defender, singleTarget, flag, method);
    damageDepth--;
    if (owner && atomic_load(&activeBattle) == battle) {
        double after = VeritasFixPoint(property(defenderAbility, 1));
        int64_t fields[4];
        for (size_t i = 0; i < sizeof(fields) / sizeof(fields[0]); i++)
            memcpy(&fields[i], (const char *)info + VeritasDamageFields[i], sizeof(fields[i]));
        double overkill;
        double damage = VeritasDamageTotal(fields, before, after, &overkill);
        if (damage > 0 || overkill > 0) {
            @autoreleasepool {
                uint32_t avatar = AvatarID(attacker);
                NSString *name = AvatarName(avatar);
                int32_t attackType;
                memcpy(&attackType, (const char *)info + VeritasAttackTypeField, sizeof(attackType));
                dispatch_async(dispatch_get_main_queue(), ^{
                    if (displayedBattle != battle) return;
                    [overlay.battle record:damage overkill:overkill owner:avatar ?: owner name:name];
                    [overlay.battle recordAttackType:attackType damage:damage owner:avatar ?: owner];
                    [overlay render];
                });
            }
        }
    }
    return result;
}

static uintptr_t DirectDamage(void *component, int64_t amount, int lockStrength, void *context,
                              void *resultAmount, void *modifier, int integerization, void *method) {
    typedef uintptr_t (*Routine)(void *, int64_t, int, void *, void *, void *, int, void *);
    unsigned battle = atomic_load(&activeBattle);
    int64_t (*property)(void *, int) = (void *)(unity + VeritasGetProperty);
    bool observe = false;
    if (battle && damageDepth == 0) {
        void *(*owner)(void *) = (void *)(unity + VeritasGetComponentOwner);
        int (*team)(void *) = (void *)(unity + VeritasGetTeam);
        void *target = owner(component);
        observe = target && team(target) == 2;
    }
    double before = observe ? VeritasFixPoint(property(component, 1)) : 0;
    damageDepth++;
    uintptr_t result = ((Routine)(unity + VeritasDirectDamageOriginal))(
        component, amount, lockStrength, context, resultAmount, modifier, integerization, method);
    damageDepth--;
    if (observe && atomic_load(&activeBattle) == battle) {
        double loss = before - VeritasFixPoint(property(component, 1));
        if (loss > 0) dispatch_async(dispatch_get_main_queue(), ^{
            if (displayedBattle != battle) return;
            [overlay.battle recordUnattributedDirectLoss:loss];
            [overlay render];
        });
    }
    return result;
}

static BOOL ConnectDamageHooks(void) {
    const char *suffix = "/UnityFramework.framework/UnityFramework";
    size_t length = strlen(suffix);
    for (uint32_t i = 0; i < _dyld_image_count(); i++) {
        const char *name = _dyld_get_image_name(i);
        if (!name || strlen(name) < length || strcmp(name + strlen(name) - length, suffix)) continue;
        uintptr_t image = (uintptr_t)_dyld_get_image_header(i);
        if (memcmp((const void *)(image + VeritasDamageEntry), VeritasDamageJump, sizeof(VeritasDamageJump)) ||
            memcmp((const void *)(image + VeritasBattleBeginEntry), VeritasBattleBeginJump, sizeof(VeritasBattleBeginJump)) ||
            memcmp((const void *)(image + VeritasBattleEndEntry), VeritasBattleEndJump, sizeof(VeritasBattleEndJump)) ||
            memcmp((const void *)(image + VeritasTurnBeginEntry), VeritasTurnBeginJump, sizeof(VeritasTurnBeginJump)) ||
            memcmp((const void *)(image + VeritasUseSkillEntry), VeritasUseSkillJump, sizeof(VeritasUseSkillJump)) ||
            memcmp((const void *)(image + VeritasDirectDamageEntry), VeritasDirectDamageJump, sizeof(VeritasDirectDamageJump))) {
            return NO;
        }
        unity = image;
        atomic_store_explicit((_Atomic(uintptr_t) *)(image + VeritasBattleBeginSlot), (uintptr_t)BattleBegin, memory_order_release);
        atomic_store_explicit((_Atomic(uintptr_t) *)(image + VeritasBattleEndSlot), (uintptr_t)BattleEnd, memory_order_release);
        atomic_store_explicit((_Atomic(uintptr_t) *)(image + VeritasTurnBeginSlot), (uintptr_t)TurnBegin, memory_order_release);
        atomic_store_explicit((_Atomic(uintptr_t) *)(image + VeritasUseSkillSlot), (uintptr_t)UseSkill, memory_order_release);
        atomic_store_explicit((_Atomic(uintptr_t) *)(image + VeritasDirectDamageSlot), (uintptr_t)DirectDamage, memory_order_release);
        atomic_store_explicit((_Atomic(uintptr_t) *)(image + VeritasDamageSlot), (uintptr_t)Damage, memory_order_release);
        return YES;
    }
    return NO;
}

__attribute__((constructor))
static void StartVeritasOverlay(void) {
    @autoreleasepool {
        if (![NSBundle.mainBundle.bundleIdentifier isEqualToString:@"com.HoYoverse.hkrpgoversea"]) return;
        if (![NSBundle.mainBundle.infoDictionary[@"CFBundleShortVersionString"] isEqual:@"4.7.0"]) return;
        dispatch_async(dispatch_get_main_queue(), ^{
            VeritasOverlay *reports = [VeritasOverlay new];
            overlay = reports;
            reports.battle = [VeritasBattle new];
            [NSUserDefaults.standardUserDefaults registerDefaults:@{
                VeritasOpacityKey: @0.8, VeritasTextSizeKey: @13,
                VeritasAttackPanelKey: @YES, VeritasSkillPanelKey: @YES,
            }];
            reports.shown = YES;
            reports.connected = ConnectDamageHooks();
            NSLog(@"[Veritas] %@", reports.connected ? @"Live combat hooks ready" : @"Live combat hooks unavailable");
            [NSNotificationCenter.defaultCenter addObserverForName:UIWindowDidBecomeKeyNotification object:nil
                queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *event) {
                    [reports attachToWindow:event.object];
                }];
            void (^attachToActiveScene)(void) = ^{
                for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
                    if (![scene isKindOfClass:UIWindowScene.class] ||
                        scene.activationState == UISceneActivationStateBackground) continue;
                    for (UIWindow *window in ((UIWindowScene *)scene).windows) {
                        if (window.isKeyWindow || (!window.hidden && window.rootViewController &&
                            window.windowLevel == UIWindowLevelNormal)) {
                            [reports attachToWindow:window];
                            break;
                        }
                    }
                }
            };
            [NSNotificationCenter.defaultCenter addObserverForName:UISceneDidActivateNotification object:nil
                queue:NSOperationQueue.mainQueue usingBlock:^(__unused NSNotification *event) {
                    attachToActiveScene();
                }];
            attachToActiveScene();
            [(id)NSClassFromString(@"NSEvent") addLocalMonitorForEventsMatchingMask:1UL << 10 handler:^id(id event) {
                NSUInteger modifiers = [event modifierFlags];
                if ((modifiers & 0x1e0000) != 0x120000 || !reports.gameWindow.isKeyWindow) return event;
                NSString *key = [[event charactersIgnoringModifiers] lowercaseString];
                BOOL visibility = [key isEqualToString:@"d"];
                if (!visibility && ![key isEqualToString:@"e"]) return event;
                if (![event isARepeat]) {
                    if (visibility) [reports toggle];
                    else [reports toggleEditing];
                }
                return nil;
            }];
        });
    }
}
