#import <Foundation/Foundation.h>
#include <math.h>

static inline double VeritasFixPoint(int64_t raw) {
    return ldexp((double)(raw & ~INT64_C(1)), raw & 1 ? -26 : -33);
}

static inline double VeritasDamageTotal(const int64_t fields[4], double before, double after, double *overkill) {
    double hp = VeritasFixPoint(fields[0]);
    double total = 0;
    for (size_t i = 0; i < 4; i++) total += fmax(0, VeritasFixPoint(fields[i]));
    *overkill = after <= 1 ? fmax(0, hp - fmax(0, before - after)) : 0;
    return fmax(0, total - *overkill);
}

static inline NSString *VeritasAttackType(int32_t type) {
    static NSString *const names[] = {
        @"Unknown", @"Basic ATK", @"Skill", @"Ultimate", @"QTE",
        @"Damage over time", @"Follow-up", @"Overworld", @"Overworld basic",
        @"Extra action", @"Elemental damage", @"Stage effect", @"Summon",
        @"True damage", @"Elation damage"
    };
    return type >= 0 && (size_t)type < sizeof(names) / sizeof(names[0]) ?
        names[type] : [NSString stringWithFormat:@"Attack type %d", type];
}

@interface VeritasBattle : NSObject
@property(nonatomic, readonly) double total;
@property(nonatomic, readonly) NSUInteger hits;
@property(nonatomic, readonly) unsigned turn;
@property(nonatomic, readonly) unsigned wave;
@property(nonatomic, readonly) double actionValue;
@property(nonatomic, readonly) double overkill;
@property(nonatomic, readonly) double unattributedDirectLoss;
@property(nonatomic, readonly) NSDictionary *series;
- (void)reset;
- (void)beginTurnAtActionValue:(double)value wave:(unsigned)wave;
- (void)record:(double)damage overkill:(double)overkill owner:(uint32_t)owner name:(NSString *)name;
- (void)recordAttackType:(int32_t)type damage:(double)damage owner:(uint32_t)owner;
- (void)recordUnattributedDirectLoss:(double)loss;
- (void)recordSkill:(NSString *)skill owner:(uint32_t)owner name:(NSString *)name;
@end

@implementation VeritasBattle {
    NSMutableArray<NSNumber *> *_history;
    NSMutableDictionary<NSString *, NSNumber *> *_owners;
    NSMutableDictionary<NSString *, NSString *> *_names;
    NSMutableArray<NSNumber *> *_turnDamage;
    double _previousActionValue;
    NSMutableDictionary<NSString *, NSMutableDictionary<NSString *, NSNumber *> *> *_attackDamage;
    NSMutableArray<NSDictionary *> *_skills;
}

- (instancetype)init {
    if ((self = [super init])) [self reset];
    return self;
}

- (void)reset {
    _total = 0;
    _hits = 0;
    _turn = _wave = 0;
    _actionValue = _previousActionValue = _overkill = _unattributedDirectLoss = 0;
    _turnDamage = [NSMutableArray arrayWithObject:@0];
    _names = [NSMutableDictionary dictionary];
    _attackDamage = [NSMutableDictionary dictionary];
    _skills = [NSMutableArray array];
    _history = [NSMutableArray arrayWithObject:@0];
    _owners = [NSMutableDictionary dictionary];
}

- (void)beginTurnAtActionValue:(double)value wave:(unsigned)wave {
    if (isfinite(value) && value >= 0) {
        _actionValue += value < _previousActionValue ? value : value - _previousActionValue;
        _previousActionValue = value;
    }
    _wave = wave;
    _turn++;
    [_turnDamage addObject:@0];
    if (_turnDamage.count > 24) [_turnDamage removeObjectAtIndex:0];
}

- (void)record:(double)damage overkill:(double)overkill owner:(uint32_t)owner name:(NSString *)name {
    if (isfinite(overkill) && overkill > 0) _overkill += overkill;
    if (!isfinite(damage) || damage <= 0) return;
    _total += damage;
    _hits++;
    [_history addObject:@(_total)];
    if (_history.count > 241) [_history removeObjectAtIndex:0];
    NSString *key = [@(owner) stringValue];
    _owners[key] = @(_owners[key].doubleValue + damage);
    if (name.length) _names[key] = name;
    _turnDamage[_turnDamage.count - 1] = @(_turnDamage.lastObject.doubleValue + damage);
}

- (void)recordAttackType:(int32_t)type damage:(double)damage owner:(uint32_t)owner {
    if (!isfinite(damage) || damage <= 0) return;
    NSString *key = [@(owner) stringValue];
    NSMutableDictionary *amounts = _attackDamage[key];
    if (!amounts) _attackDamage[key] = amounts = [NSMutableDictionary dictionary];
    NSString *label = VeritasAttackType(type);
    amounts[label] = @([amounts[label] doubleValue] + damage);
}

- (void)recordUnattributedDirectLoss:(double)loss {
    if (isfinite(loss) && loss > 0) _unattributedDirectLoss += loss;
}

- (void)recordSkill:(NSString *)skill owner:(uint32_t)owner name:(NSString *)name {
    if (!skill.length) return;
    NSString *key = [@(owner) stringValue];
    if (name.length) _names[key] = name;
    [_skills addObject:@{@"owner": key, @"skill": skill, @"turn": @(_turn)}];
    if (_skills.count > 32) [_skills removeObjectAtIndex:0];
}

- (NSDictionary *)series {
    NSMutableDictionary *attackDamage = [NSMutableDictionary dictionaryWithCapacity:_attackDamage.count];
    [_attackDamage enumerateKeysAndObjectsUsingBlock:^(NSString *key, NSDictionary *amounts, __unused BOOL *stop) {
        attackDamage[key] = [amounts copy];
    }];
    return @{@"history": [_history copy], @"avatars": [_owners copy],
             @"names": [_names copy], @"turns": [_turnDamage copy],
             @"attackDamage": attackDamage, @"skills": [_skills copy]};
}

@end
