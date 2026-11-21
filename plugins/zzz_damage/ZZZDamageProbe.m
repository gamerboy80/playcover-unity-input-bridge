#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <mach-o/dyld.h>
#include <os/lock.h>
#include <stdatomic.h>
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <time.h>
#import "Meter.h"

@interface NSObject (ProbeKeyboardMonitor)
+ (id)addLocalMonitorForEventsMatchingMask:(NSUInteger)mask handler:(id (^)(id))handler;
@end

@protocol ProbeKeyEvent
- (NSUInteger)modifierFlags;
- (unsigned short)keyCode;
- (BOOL)isARepeat;
@end

typedef struct ProbeFrame {
    ProbeEvent event;
    ProbeEntity source, target;
    uint32_t avatarID;
    uint16_t sourceName[MeterNameCapacity];
    struct ProbeFrame *previous;
} ProbeFrame;

static _Thread_local ProbeFrame *frame;
static uintptr_t unity;
static BOOL objectNamesAvailable;
static BOOL avatarLookupAvailable;
static BOOL avatarNamesAvailable;
static NSMutableDictionary<NSNumber *, NSString *> *avatarNames;
static dispatch_queue_t writer;
static FILE *logFile;
static atomic_uint phase, events, markers;
static id keyboardMonitor;
static os_unfair_lock meterLock = OS_UNFAIR_LOCK_INIT;
static DamageMeter meter;
static UIWindow *meterWindow;
static UILabel *meterLabel;
static BOOL meterVisible = YES;

@interface ZZZMeterWindow : UIWindow
@end
@implementation ZZZMeterWindow
- (UIView *)hitTest:(CGPoint)point withEvent:(UIEvent *)event {
    (void)point;
    (void)event;
    return nil;
}
@end

static double Now(void) {
    struct timespec time;
    clock_gettime(CLOCK_MONOTONIC_RAW, &time);
    return time.tv_sec + time.tv_nsec * 1e-9;
}

static int MostDamageFirst(const void *a, const void *b) {
    const MeterSource *left = a, *right = b;
    if (left->damage != right->damage) return left->damage > right->damage ? -1 : 1;
    return (left->id > right->id) - (left->id < right->id);
}

static NSString *Amount(double amount) {
    return [NSNumberFormatter localizedStringFromNumber:@(round(amount)) numberStyle:NSNumberFormatterDecimalStyle];
}

static NSString *GameString(const char *value) {
    if (!value) return nil;
    uint32_t length = ProbeU32(value, ProbeStringLength);
    if (!length || length >= MeterNameCapacity) return nil;
    const uint16_t *characters = (const void *)(value + ProbeStringCharacters);
    NSString *text = [NSString stringWithCharacters:characters length:length];
    if ([text rangeOfCharacterFromSet:NSCharacterSet.controlCharacterSet].location != NSNotFound) return nil;
    return text;
}

static NSString *AvatarLabel(uint32_t avatarID) {
    NSNumber *identifier = @(avatarID);
    NSString *label = avatarNames[identifier];
    if (label) return label;
    if (avatarNamesAvailable) {
        const char *(*nameForID)(uint32_t, bool, void *) = (void *)(unity + ProbeAvatarName);
        const char *(*translate)(const char *, uint16_t, void *) = (void *)(unity + ProbeLocalizedText);
        const char *value = nameForID(avatarID, true, NULL);
        NSString *name = GameString(value);
        if ([name containsString:@"_"]) {
            label = GameString(translate(value, 0, NULL));
            if ([label isEqualToString:name]) label = nil;
        } else {
            label = name;
        }
    }
    if (!label.length) label = [NSString stringWithFormat:@"Agent %u", avatarID];
    if (!avatarNames) avatarNames = [NSMutableDictionary new];
    avatarNames[identifier] = label;
    return label;
}

static NSString *SourceLabel(MeterSource source) {
    if (source.avatarID) return AvatarLabel(source.avatarID);
    size_t length = 0;
    while (length < MeterNameCapacity && source.name[length]) ++length;
    if (!length) return [NSString stringWithFormat:@"Source %u", source.id];
    NSString *name = [NSString stringWithCharacters:source.name length:length];
    return [NSString stringWithFormat:@"%@ (#%u)", name, source.id];
}

static uint32_t ReadAvatarID(void *entity) {
    if (!avatarLookupAvailable || !NSThread.isMainThread) return 0;
    void *(*actorForEntity)(void *, void *) = (void *)(unity + ProbeAvatarActor);
    void *(*dataForActor)(void *, void *) = (void *)(unity + ProbeAvatarData);
    void *actor = actorForEntity(entity, NULL);
    void *data = actor ? dataForActor(actor, NULL) : NULL;
    return data ? ProbeU32(data, ProbeAvatarTemplateID) : 0;
}

static void ReadSourceName(void *entity, uint16_t *out) {
    if (!objectNamesAvailable || !entity || !NSThread.isMainThread) return;
    void *root, *cached;
    memcpy(&root, (const char *)entity + ProbeEntityRoot, sizeof(root));
    if (!root) return;
    memcpy(&cached, (const char *)root + ProbeUnityCachedPointer, sizeof(cached));
    if (!cached) return;
    void *(*nameGetter)(void *, void *) = (void *)(unity + ProbeObjectName);
    const char *name = nameGetter(root, NULL);
    if (!name) return;
    uint32_t length = ProbeU32(name, ProbeStringLength);
    if (length > 96) return;
    MeterCopyName(out, (const uint16_t *)(name + ProbeStringCharacters), length);
}

static void RefreshMeter(void) {
    if (!meterVisible) return;
    UIWindow *game = nil;
    for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
        if (![scene isKindOfClass:UIWindowScene.class] ||
            scene.activationState != UISceneActivationStateForegroundActive) continue;
        for (UIWindow *window in ((UIWindowScene *)scene).windows) {
            if (window.isKeyWindow && ![window isKindOfClass:ZZZMeterWindow.class]) {
                game = window;
                break;
            }
        }
        if (game) break;
    }
    if (!game) return;
    if (meterWindow.windowScene != game.windowScene) {
        meterWindow.hidden = YES;
        meterWindow = [[ZZZMeterWindow alloc] initWithWindowScene:game.windowScene];
        meterWindow.windowLevel = game.windowLevel + 1;
        meterWindow.userInteractionEnabled = NO;
        meterWindow.rootViewController = [UIViewController new];
        UIView *root = meterWindow.rootViewController.view;
        root.backgroundColor = UIColor.clearColor;
        UIView *panel = [UIView new];
        panel.backgroundColor = [UIColor colorWithWhite:0.07 alpha:0.86];
        panel.layer.cornerRadius = 10;
        panel.translatesAutoresizingMaskIntoConstraints = NO;
        [root addSubview:panel];
        meterLabel = [UILabel new];
        meterLabel.translatesAutoresizingMaskIntoConstraints = NO;
        meterLabel.numberOfLines = 0;
        meterLabel.font = [UIFont monospacedDigitSystemFontOfSize:13 weight:UIFontWeightMedium];
        meterLabel.textColor = UIColor.whiteColor;
        [panel addSubview:meterLabel];
        UILayoutGuide *safe = root.safeAreaLayoutGuide;
        [NSLayoutConstraint activateConstraints:@[
            [panel.topAnchor constraintEqualToAnchor:safe.topAnchor constant:14],
            [panel.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-14],
            [panel.leadingAnchor constraintGreaterThanOrEqualToAnchor:safe.leadingAnchor constant:14],
            [meterLabel.leadingAnchor constraintEqualToAnchor:panel.leadingAnchor constant:12],
            [meterLabel.trailingAnchor constraintEqualToAnchor:panel.trailingAnchor constant:-12],
            [meterLabel.topAnchor constraintEqualToAnchor:panel.topAnchor constant:9],
            [meterLabel.bottomAnchor constraintEqualToAnchor:panel.bottomAnchor constant:-9],
        ]];
    }
    meterWindow.hidden = NO;
    os_unfair_lock_lock(&meterLock);
    DamageMeter snapshot = meter;
    os_unfair_lock_unlock(&meterLock);
    NSMutableString *display = [NSMutableString stringWithString:@"ZZZ · Damage display events"];
    if (!snapshot.total) {
        [display appendString:@"\nWaiting for damage"];
    } else {
        double elapsed = snapshot.last - snapshot.first;
        [display appendFormat:@"\n%@ raw total", Amount(snapshot.total)];
        if (elapsed > 0) [display appendFormat:@"  ·  %@ raw/s  ·  %.1fs", Amount(snapshot.total / elapsed), elapsed];
        [display appendFormat:@"\nLatest: %@", SourceLabel(snapshot.latestSource)];
        qsort(snapshot.sources, snapshot.count, sizeof(snapshot.sources[0]), MostDamageFirst);
        double remaining = snapshot.other;
        for (unsigned i = 0; i < snapshot.count; ++i) {
            MeterSource source = snapshot.sources[i];
            if (i < 5) {
                [display appendFormat:@"\n%@   %@   %.1f%%", SourceLabel(source), Amount(source.damage),
                                      100 * source.damage / snapshot.total];
            } else remaining += source.damage;
        }
        if (remaining > 0) [display appendFormat:@"\nOther      %@   %.1f%%", Amount(remaining), 100 * remaining / snapshot.total];
    }
    if (![meterLabel.text isEqualToString:display]) meterLabel.text = display;
}

static void Write(NSDictionary *record) {
    if (!logFile) return;
    NSData *json = [NSJSONSerialization dataWithJSONObject:record options:NSJSONWritingSortedKeys error:NULL];
    if (!json || fwrite(json.bytes, 1, json.length, logFile) != json.length ||
        fputc('\n', logFile) == EOF || fflush(logFile)) {
        fclose(logFile);
        logFile = NULL;
        NSLog(@"[ZZZDamageProbe] Capture stopped: could not write diagnostic log");
    }
}

static NSDictionary *Resolution(ProbeEntity entity) {
    return @{@"observed": @(entity.observed), @"matches": @(entity.matches),
             @"id": @(entity.id), @"kind": @(entity.kind)};
}

static void *LookupEntity(void *manager, uint32_t identifier, void *method) {
    void *(*original)(void *, uint32_t, void *) = (void *)(unity + ProbeLookupEntityOriginal);
    void *result = original(manager, identifier, method);
    if (frame) {
        if (identifier == frame->event.source) {
            frame->source = ProbeResolve(result, identifier);
            if (frame->source.matches && frame->source.kind == 1 && !frame->avatarID) {
                frame->avatarID = ReadAvatarID(result);
                if (!frame->avatarID && !frame->sourceName[0]) ReadSourceName(result, frame->sourceName);
            }
        }
        if (identifier == frame->event.target) frame->target = ProbeResolve(result, identifier);
    }
    return result;
}

static void DamageEvent(void *controller, const void *payload, void *method) {
    void (*original)(void *, const void *, void *) = (void *)(unity + ProbeDamageEventOriginal);
    if (!payload) {
        original(controller, payload, method);
        return;
    }
    ProbeFrame current = {.event = ProbeDecode(payload), .previous = frame};
    double time = Now();
    unsigned capturedPhase = atomic_load(&phase);
    frame = &current;
    @try {
        original(controller, payload, method);
    } @finally {
        frame = current.previous;
    }
    ProbeEvent event = current.event;
    ProbeEntity source = current.source, target = current.target;
    uint32_t avatarID = current.avatarID;
    if (ProbeCountsDamage(event, source, target)) {
        MeterSource hit = {.id = event.source, .avatarID = avatarID, .damage = event.amount};
        memcpy(hit.name, current.sourceName, sizeof(hit.name));
        MeterDropRuntimeName(&hit);
        os_unfair_lock_lock(&meterLock);
        MeterRecord(&meter, hit, time);
        os_unfair_lock_unlock(&meterLock);
    }
    unsigned sequence = atomic_fetch_add(&events, 1);
    if (sequence >= 4096) return;
    dispatch_async(writer, ^{
        @autoreleasepool {
            Write(@{@"type": @"damage_candidate", @"sequence": @(sequence + 1),
                    @"time": @(time), @"phase": @(capturedPhase),
                    @"target_id": @(event.target), @"source_id": @(event.source),
                    @"source_avatar_id": @(avatarID),
                    @"amount": isfinite(event.amount) ? @(event.amount) : NSNull.null,
                    @"kind": @(event.kind), @"hidden": @(event.hidden),
                    @"suppressed": @(event.suppressed),
                    @"source_lookup": Resolution(source), @"target_lookup": Resolution(target)});
            if (sequence == 4095) Write(@{@"type": @"limit", @"events": @4096});
        }
    });
}

static BOOL Connect(void) {
    const char *suffix = "/UnityFramework.framework/UnityFramework";
    for (uint32_t i = 0; i < _dyld_image_count(); i++) {
        const char *name = _dyld_get_image_name(i);
        size_t length = name ? strlen(name) : 0;
        if (length < strlen(suffix) || strcmp(name + length - strlen(suffix), suffix)) continue;
        const struct mach_header_64 *header = (const void *)_dyld_get_image_header(i);
        const uint8_t *command = (const void *)(header + 1);
        BOOL uuidMatches = NO;
        for (uint32_t j = 0; j < header->ncmds; j++) {
            const struct load_command *load = (const void *)command;
            if (load->cmd == LC_UUID) {
                const struct uuid_command *uuid = (const void *)command;
                uuidMatches = !memcmp(uuid->uuid, ProbeUUID, sizeof(ProbeUUID));
            }
            command += load->cmdsize;
        }
        uintptr_t image = (uintptr_t)header;
        if (!uuidMatches ||
            memcmp((void *)(image + ProbeDamageEventEntry), ProbeDamageEventJump, sizeof(ProbeDamageEventJump)) ||
            memcmp((void *)(image + ProbeDamageEventStub), ProbeDamageEventCode, sizeof(ProbeDamageEventCode)) ||
            memcmp((void *)(image + ProbeLookupEntityEntry), ProbeLookupEntityJump, sizeof(ProbeLookupEntityJump)) ||
            memcmp((void *)(image + ProbeLookupEntityStub), ProbeLookupEntityCode, sizeof(ProbeLookupEntityCode))) return NO;
        _Atomic(uintptr_t) *lookupSlot = (void *)(image + ProbeLookupEntitySlot);
        _Atomic(uintptr_t) *damageSlot = (void *)(image + ProbeDamageEventSlot);
        if (atomic_load(lookupSlot) || atomic_load(damageSlot)) return NO;
        unity = image;
        objectNamesAvailable = !memcmp((void *)(image + ProbeObjectName), ProbeObjectNameCode, sizeof(ProbeObjectNameCode));
        avatarLookupAvailable =
            !memcmp((void *)(image + ProbeAvatarActor), ProbeAvatarActorCode, sizeof(ProbeAvatarActorCode)) &&
            !memcmp((void *)(image + ProbeAvatarData), ProbeAvatarDataCode, sizeof(ProbeAvatarDataCode));
        avatarNamesAvailable =
            !memcmp((void *)(image + ProbeAvatarName), ProbeAvatarNameCode, sizeof(ProbeAvatarNameCode)) &&
            !memcmp((void *)(image + ProbeLocalizedText), ProbeLocalizedTextCode, sizeof(ProbeLocalizedTextCode));
        atomic_store_explicit(lookupSlot, (uintptr_t)LookupEntity, memory_order_release);
        atomic_store_explicit(damageSlot, (uintptr_t)DamageEvent, memory_order_release);
        return YES;
    }
    return NO;
}

__attribute__((constructor))
static void StartProbe(void) {
    @autoreleasepool {
        NSBundle *bundle = NSBundle.mainBundle;
        if (![bundle.bundleIdentifier isEqualToString:@"com.HoYoverse.Nap"] ||
            ![bundle.infoDictionary[@"CFBundleShortVersionString"] isEqual:@"3.3.1"] ||
            ![bundle.infoDictionary[@"CFBundleVersion"] isEqual:@"4"]) return;
        dispatch_async(dispatch_get_main_queue(), ^{
            NSString *directory = [NSHomeDirectory() stringByAppendingPathComponent:@"Documents/LogDir"];
            if (![NSFileManager.defaultManager createDirectoryAtPath:directory
                    withIntermediateDirectories:YES attributes:nil error:NULL]) return;
            NSString *filename = [NSString stringWithFormat:@"ZZZDamageProbe-%@.jsonl", NSUUID.UUID.UUIDString];
            NSString *path = [directory stringByAppendingPathComponent:filename];
            int descriptor = open(path.fileSystemRepresentation, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
            if (descriptor < 0) return;
            logFile = fdopen(descriptor, "w");
            if (!logFile) { close(descriptor); return; }
            writer = dispatch_queue_create("ZZZDamageProbe.writer", DISPATCH_QUEUE_SERIAL);
            // Enqueue the session before publishing callbacks to game threads.
            dispatch_sync(writer, ^{
                Write(@{@"type": @"session", @"schema": @1, @"version": @"3.3.1", @"build": @"4",
                        @"runtime_verified": @NO, @"event_limit": @4096});
            });
            BOOL connected = Connect();
            dispatch_async(writer, ^{ Write(@{@"type": @"hooks", @"ready": @(connected)}); });
            NSLog(@"[ZZZDamageProbe] %@; diagnostic log: %@", connected ? @"Ready" : @"Hooks unavailable", path);
            if (!connected) return;
            [NSTimer scheduledTimerWithTimeInterval:0.25 repeats:YES block:^(__unused NSTimer *timer) {
                RefreshMeter();
            }];
            keyboardMonitor = [NSClassFromString(@"NSEvent") addLocalMonitorForEventsMatchingMask:1UL << 10
                handler:^id(id event) {
                    id<ProbeKeyEvent> keyEvent = event;
                    NSUInteger modifiers = [keyEvent modifierFlags];
                    unsigned short key = [keyEvent keyCode];
                    if (ProbeMeterShortcut(modifiers) && (key == 2 || key == 15)) {
                        if ([keyEvent isARepeat]) return nil;
                        if (key == 2) {
                            meterVisible = !meterVisible;
                            meterWindow.hidden = !meterVisible;
                        } else {
                            os_unfair_lock_lock(&meterLock);
                            meter = (DamageMeter){.resetAt = Now()};
                            os_unfair_lock_unlock(&meterLock);
                            [avatarNames removeAllObjects];
                        }
                        RefreshMeter();
                        return nil;
                    }
                    int value = ProbePhaseForKey(modifiers, key);
                    if (value < 0) return event;
                    if ([keyEvent isARepeat]) return nil;
                    if (atomic_fetch_add(&markers, 1) >= 64) return event;
                    atomic_store(&phase, value);
                    double time = Now();
                    dispatch_async(writer, ^{ Write(@{@"type": @"marker", @"phase": @(value), @"time": @(time)}); });
                    NSLog(@"[ZZZDamageProbe] Training phase %d", value);
                    return nil;
                }];
        });
    }
}
