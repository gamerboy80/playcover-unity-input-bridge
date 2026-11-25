#import <Foundation/Foundation.h>
#include <math.h>

static inline double VeritasFixPoint(int64_t raw) {
    return ldexp((double)(raw & ~INT64_C(1)), raw & 1 ? -26 : -33);
}

static inline double VeritasDamageTotal(const int64_t fields[4], double before, double after, double *overkill) {
    double hp = VeritasFixPoint(fields[0]), total = 0;
    for (size_t i = 0; i < 4; i++) total += fmax(0, VeritasFixPoint(fields[i]));
    *overkill = after <= 1 ? fmax(0, hp - fmax(0, before - after)) : 0;
    return total;
}

static NSDictionary<NSNumber *, NSString *> *VeritasNativeAttackNames;
static inline NSString *VeritasAttackSymbol(int32_t type) {
    NSString *symbol = VeritasNativeAttackNames[@(type)];
    if (symbol) return symbol;
    static NSString *const symbols[] = {@"Unknown", @"Normal", @"BPSkill", @"Ultra", @"QTE", @"DOT", @"Pursued",
        @"Maze", @"MazeNormal", @"Insert", @"ElementDamage", @"Level", @"Servant", @"TrueDamage", @"ElationDamage", @"Assist"};
    return type >= 0 && (size_t)type < sizeof(symbols) / sizeof(symbols[0]) ? symbols[type] :
        [NSString stringWithFormat:@"Attack type %d", type];
}
static inline NSString *VeritasAttackType(int32_t type) {
    static NSDictionary *labels; static dispatch_once_t once;
    dispatch_once(&once, ^{ labels = @{@"Normal": @"Basic", @"BPSkill": @"Skill", @"Ultra": @"Ultimate", @"DOT": @"DoT",
        @"Pursued": @"Additional", @"Maze": @"Technique", @"MazeNormal": @"Technique", @"Insert": @"Follow-Up",
        @"ElementDamage": @"Break", @"TrueDamage": @"True", @"ElationDamage": @"Elation"}; });
    NSString *symbol = VeritasAttackSymbol(type);
    return labels[symbol] ?: symbol;
}

static inline NSDictionary *VeritasEntity(uint32_t uid, BOOL player) {
    return @{@"uid": @(uid), @"team": player ? @"Player" : @"Enemy"};
}

@interface VeritasBattle : NSObject
@property(nonatomic, readonly) double total;
@property(nonatomic, readonly) NSUInteger hits;
@property(nonatomic, readonly) unsigned turn;
@property(nonatomic) unsigned wave;
@property(nonatomic) unsigned cycle;
@property(nonatomic) unsigned maxWave;
@property(nonatomic) unsigned maxCycle;
@property(nonatomic) unsigned stage;
@property(nonatomic, readonly) double actionValue;
@property(nonatomic, readonly) double resetActionValue;
@property(nonatomic, readonly) double overkill;
@property(nonatomic, readonly) double unattributedDirectLoss;
@property(nonatomic, readonly) NSDictionary *series;
@property(nonatomic, copy) void (^eventSink)(NSString *, NSDictionary *);
- (void)reset;
- (void)setLineup:(NSArray<NSDictionary *> *)lineup;
- (void)beginTurnAtActionValue:(double)value wave:(unsigned)wave;
- (void)setTurnOwner:(NSDictionary *)entity;
- (void)endTurn;
- (void)resetAV:(double)value;
- (void)record:(double)damage overkill:(double)overkill owner:(uint32_t)owner name:(NSString *)name;
- (void)recordAttackType:(int32_t)type damage:(double)damage owner:(uint32_t)owner;
- (void)recordUnattributedDirectLoss:(double)loss;
- (void)recordSkill:(NSString *)skill owner:(uint32_t)owner name:(NSString *)name;
- (void)recordSkill:(NSString *)skill type:(int)type owner:(uint32_t)owner name:(NSString *)name;
- (void)recordSkill:(NSString *)skill type:(int)type configID:(uint32_t)configID owner:(uint32_t)owner name:(NSString *)name;
- (void)updateEntity:(NSDictionary *)entity name:(NSString *)name stats:(NSDictionary *)stats;
- (void)initializeEnemy:(NSDictionary *)enemy;
- (void)setFormation:(NSArray *)entities player:(BOOL)player;
- (void)defeat:(NSDictionary *)entity killer:(NSDictionary *)killer;
- (NSDictionary *)snapshot;
@end

@implementation VeritasBattle {
    NSMutableArray *_history, *_turns, *_skills, *_turnHistory, *_avHistory, *_entityTurns, *_lineup, *_events;
    NSMutableDictionary *_owners, *_names, *_attackDamage, *_overkills, *_entities, *_enemies;
    NSMutableDictionary *_currentDamage;
    NSArray *_enemyFormation;
    double _previousActionValue, _lastOverkill;
    NSDictionary *_turnOwner;
    BOOL _turnOpen, _formationKnown;
    NSUInteger _droppedEvents;
}
- (instancetype)init { if ((self = [super init])) [self reset]; return self; }
- (void)emit:(NSString *)name data:(NSDictionary *)data {
    if (_events.count < 200000) [_events addObject:@{@"type": name, @"data": data}];
    else _droppedEvents++;
    if (self.eventSink) self.eventSink(name, data);
}
- (void)reset {
    _lastOverkill = 0;
    _total = _overkill = _unattributedDirectLoss = _actionValue = _previousActionValue = _resetActionValue = 0;
    _hits = _turn = _wave = _cycle = _maxWave = _maxCycle = _stage = 0;
    _turnOpen = NO; _formationKnown = NO; _turnOwner = nil; _droppedEvents = 0;
    _history = [NSMutableArray arrayWithObject:@0]; _turns = [NSMutableArray arrayWithObject:@0];
    _owners = [NSMutableDictionary dictionary]; _names = [NSMutableDictionary dictionary];
    _overkills = [NSMutableDictionary dictionary]; _attackDamage = [NSMutableDictionary dictionary];
    _skills = [NSMutableArray array]; _turnHistory = [NSMutableArray array]; _avHistory = [NSMutableArray array];
    _entityTurns = [NSMutableArray array]; _lineup = [NSMutableArray array]; _events = [NSMutableArray array];
    _entities = [NSMutableDictionary dictionary]; _enemies = [NSMutableDictionary dictionary];
    _currentDamage = [NSMutableDictionary dictionary]; _enemyFormation = @[];
}
- (void)setLineup:(NSArray<NSDictionary *> *)lineup {
    _lineup = [lineup mutableCopy];
    for (NSDictionary *avatar in lineup) {
        NSString *key = [avatar[@"id"] stringValue];
        _names[key] = avatar[@"name"] ?: key;
        if (!_owners[key]) _owners[key] = @0;
    }
    [self emit:@"OnSetBattleLineup" data:@{@"avatars": [_lineup copy]}];
}
- (void)beginTurnAtActionValue:(double)value wave:(unsigned)wave {
    if (_turnOpen) [self endTurn];
    if (isfinite(value) && value >= 0) {
        // Elapsed AV resets across waves; keep the cumulative axis continuous.
        _actionValue += value < _previousActionValue ? value : value - _previousActionValue;
        _previousActionValue = value;
    }
    _wave = wave; _turn++; _turnOpen = YES;
    _currentDamage = [NSMutableDictionary dictionary];
    [_turns addObject:@0];
}
- (void)setTurnOwner:(NSDictionary *)entity {
    _turnOwner = entity;
    if (entity) [_entityTurns addObject:@{@"entity": entity, @"action_value": @(_actionValue),
        @"wave": @(_wave), @"cycle": @(_cycle), @"turn": @(_turn)}];
    [self emit:@"OnTurnBegin" data:@{@"action_value": @(_actionValue), @"turn_owner": entity ?: NSNull.null}];
}
- (void)endTurn {
    if (!_turnOpen) return;
    NSMutableArray *amounts = [NSMutableArray array];
    for (NSDictionary *avatar in _lineup) [amounts addObject:_currentDamage[[avatar[@"id"] stringValue]] ?: @0];
    double sum = [[_currentDamage.allValues valueForKeyPath:@"@sum.self"] doubleValue];
    NSDictionary *info = @{@"action_value": @(_actionValue), @"wave": @(_wave), @"cycle": @(_cycle),
        @"turn": @(_turn), @"avatars_turn_damage": amounts, @"damage_by_owner": [_currentDamage copy],
        @"total_damage": @(sum), @"owner": _turnOwner ?: NSNull.null};
    [_turnHistory addObject:info];
    NSMutableDictionary *last = _avHistory.lastObject;
    if (last && [last[@"action_value"] doubleValue] == _actionValue) {
        NSMutableDictionary *combined = [last[@"damage_by_owner"] mutableCopy];
        for (NSString *key in _currentDamage) combined[key] = @([combined[key] doubleValue] + [_currentDamage[key] doubleValue]);
        last[@"damage_by_owner"] = combined;
        last[@"total_damage"] = @([last[@"total_damage"] doubleValue] + sum);
        NSMutableArray *avAmounts = [NSMutableArray array];
        for (NSDictionary *avatar in _lineup) [avAmounts addObject:combined[[avatar[@"id"] stringValue]] ?: @0];
        last[@"avatars_turn_damage"] = avAmounts;
    } else [_avHistory addObject:[info mutableCopy]];
    _turnOpen = NO;
    [self emit:@"OnTurnEnd" data:@{@"turn_info": info}];
}
- (void)resetAV:(double)value {
    if (!isfinite(value) || value < 0) return;
    _actionValue += value < _previousActionValue ? value : value - _previousActionValue;
    _previousActionValue = value;
    _resetActionValue = _actionValue;
}
- (void)ensureOwner:(uint32_t)owner name:(NSString *)name {
    NSString *key = [@(owner) stringValue];
    if (name.length) _names[key] = name;
    if (!_owners[key]) {
        _owners[key] = @0;
        [_lineup addObject:@{@"id": @(owner), @"name": name ?: key}];
    }
}
- (void)record:(double)damage overkill:(double)overkill owner:(uint32_t)owner name:(NSString *)name {
    if (!isfinite(damage) || damage < 0 || !owner) return;
    [self ensureOwner:owner name:name];
    NSString *key = [@(owner) stringValue];
    _lastOverkill = isfinite(overkill) ? fmax(0, overkill) : 0;
    if (isfinite(overkill) && overkill > 0) {
        _overkill += overkill; _overkills[key] = @([_overkills[key] doubleValue] + overkill);
    }
    if (damage == 0) return;
    _total += damage; _hits++;
    [_history addObject:@(_total)];
    _owners[key] = @([_owners[key] doubleValue] + damage);
    _currentDamage[key] = @([_currentDamage[key] doubleValue] + damage);
    _turns[_turns.count - 1] = @([_turns.lastObject doubleValue] + damage);
}
- (void)recordAttackType:(int32_t)type damage:(double)damage owner:(uint32_t)owner {
    if (!isfinite(damage) || damage <= 0) return;
    NSString *key = [@(owner) stringValue], *label = VeritasAttackType(type);
    NSMutableDictionary *amounts = _attackDamage[key];
    if (!amounts) _attackDamage[key] = amounts = [NSMutableDictionary dictionary];
    amounts[label] = @([amounts[label] doubleValue] + damage);
    // Match upstream: skill damage is the owner's subsequent damage, including delayed effects.
    for (NSMutableDictionary *skill in _skills.reverseObjectEnumerator) {
        if (![skill[@"owner"] isEqual:key]) continue;
        skill[@"total_damage"] = @([skill[@"total_damage"] doubleValue] + damage);
        [skill[@"damage_detail"] addObject:@{@"damage": @(damage), @"overkill_damage": @(_lastOverkill), @"type": label}];
        break;
    }
    [self emit:@"OnDamage" data:@{@"attacker": VeritasEntity(owner, YES), @"damage": @(damage),
        @"overkill_damage": @(_lastOverkill), @"type": label}];
}
- (void)recordUnattributedDirectLoss:(double)loss {
    if (isfinite(loss) && loss > 0) _unattributedDirectLoss += loss;
}
- (void)recordSkill:(NSString *)skill owner:(uint32_t)owner name:(NSString *)name {
    [self recordSkill:skill type:0 owner:owner name:name];
}
- (void)recordSkill:(NSString *)skill type:(int)type owner:(uint32_t)owner name:(NSString *)name {
    [self recordSkill:skill type:type configID:0 owner:owner name:name];
}
- (void)recordSkill:(NSString *)skill type:(int)type configID:(uint32_t)configID owner:(uint32_t)owner name:(NSString *)name {
    if (!skill.length || !owner) return;
    [self ensureOwner:owner name:name];
    [_skills addObject:[@{@"owner": [@(owner) stringValue], @"skill": skill, @"skill_type": VeritasAttackSymbol(type), @"skill_config_id": @(configID), @"turn": @(_turn),
        @"total_damage": @0, @"damage_detail": [NSMutableArray array], @"action_value": @(_actionValue),
        @"wave": @(_wave), @"cycle": @(_cycle)} mutableCopy]];
    [self emit:@"OnUseSkill" data:@{@"avatar": VeritasEntity(owner, YES),
        @"skill": @{@"name": skill, @"type": VeritasAttackSymbol(type), @"skill_config_id": @(configID)}}];
}
- (void)updateEntity:(NSDictionary *)entity name:(NSString *)name stats:(NSDictionary *)stats {
    if ([entity[@"team"] isEqual:@"Player"]) [self ensureOwner:[entity[@"uid"] unsignedIntValue] name:name];
    NSString *key = [NSString stringWithFormat:@"%@:%@", entity[@"team"], entity[@"uid"]];
    NSMutableDictionary *record = _entities[key];
    if (!record) _entities[key] = record = [@{@"entity": entity, @"stats": [NSMutableDictionary dictionary],
        @"stats_history": [NSMutableArray array], @"name": name ?: [entity[@"uid"] stringValue]} mutableCopy];
    if (name.length) record[@"name"] = name;
    NSMutableDictionary *properties = record[@"stats"];
    NSMutableDictionary *changes = [NSMutableDictionary dictionary];
    for (NSString *property in stats) {
        NSNumber *value = stats[property];
        if (!isfinite(value.doubleValue) || [properties[property] isEqual:value]) continue;
        changes[property] = value; properties[property] = value;
        [self emit:@"OnStatChange" data:@{@"entity": entity, @"property": @{@"type": property, @"value": value}}];
    }
    if (changes.count) {
        NSMutableArray *history = record[@"stats_history"];
        NSMutableDictionary *last = history.lastObject;
        if (last && [last[@"turn_battle_id"] unsignedIntValue] == _turn) [last[@"stats"] addEntriesFromDictionary:changes];
        else [history addObject:[@{@"turn_battle_id": @(_turn), @"stats": changes} mutableCopy]];
    }
}
- (void)initializeEnemy:(NSDictionary *)enemy {
    _enemies[[enemy[@"uid"] stringValue]] = enemy;
    [self updateEntity:VeritasEntity([enemy[@"uid"] unsignedIntValue], NO) name:enemy[@"name"] stats:enemy[@"base_stats"][@"properties"]];
    [self emit:@"OnInitializeEnemy" data:@{@"enemy": enemy}];
}
- (void)setFormation:(NSArray *)entities player:(BOOL)player {
    if (!player) { _enemyFormation = [entities copy]; _formationKnown = YES; }
    [self emit:@"OnUpdateTeamFormation" data:@{@"entities": entities, @"team": player ? @"Player" : @"Enemy"}];
}
- (void)defeat:(NSDictionary *)entity killer:(NSDictionary *)killer {
    NSString *key = [NSString stringWithFormat:@"%@:%@", entity[@"team"], entity[@"uid"]];
    NSMutableDictionary *record = _entities[key];
    if (!record || [record[@"is_die"] boolValue]) return;
    record[@"is_die"] = @YES; record[@"killer"] = killer ?: NSNull.null;
    [self emit:@"OnEntityDefeated" data:@{@"entity_defeated": entity, @"killer": killer ?: NSNull.null}];
}
- (NSDictionary *)series {
    return @{@"history": [_history copy], @"avatars": [_owners copy], @"names": [_names copy],
        @"turns": [_turns copy], @"attackDamage": _attackDamage, @"skills": _skills,
        @"overkills": _overkills, @"turn_history": _turnHistory, @"av_history": _avHistory,
        @"entity_turn_history": _entityTurns, @"lineup": _lineup, @"entities": _entities,
        @"enemies": _enemies, @"enemy_formation": _enemyFormation, @"enemy_formation_known": @(_formationKnown),
        @"current_turn": @{@"action_value": @(_actionValue), @"turn": @(_turn), @"damage_by_owner": [_currentDamage copy]}};
}
- (NSDictionary *)snapshot {
    NSMutableDictionary *data = [self.series mutableCopy];
    [data addEntriesFromDictionary:@{@"schema_version": @1, @"version": @"PlayCover-1", @"total_damage": @(_total),
        @"overkill_damage": @(_overkill), @"hits": @(_hits), @"turn_count": @(_turn),
        @"action_value": @(_actionValue), @"reset_action_value": @(_resetActionValue),
        @"damage_per_av": @(_actionValue > 0 ? _total / _actionValue : _total),
        @"wave": @(_wave), @"cycle": @(_cycle), @"max_wave": @(_maxWave), @"max_cycle": @(_maxCycle),
        @"stage_id": @(_stage), @"unattributed_direct_loss": @(_unattributedDirectLoss),
        @"events": _events, @"dropped_events": @(_droppedEvents)}];
    // Freeze nested collections before crossing queues or retaining a previous battle.
    return [NSJSONSerialization JSONObjectWithData:[NSJSONSerialization dataWithJSONObject:data options:0 error:NULL] options:0 error:NULL];
}
@end
