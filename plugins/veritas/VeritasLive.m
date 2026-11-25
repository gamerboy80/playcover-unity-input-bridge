#import <UIKit/UIKit.h>
#import <mach-o/dyld.h>
#include <stdatomic.h>
#include <string.h>
#import "Telemetry.h"
#import "VeritasProfile.h"

#import "Overlay.h"

typedef uintptr_t (*DamageRoutine)(void *, void *, const void *, void *, void *,
                                   void *, void *, void *, bool, void *);
typedef void (*BattleRoutine)(void *, void *);

static uintptr_t unity;
static VeritasOverlay *overlay;
static _Atomic(unsigned) activeBattle;
static _Atomic(unsigned) nextBattle;
static unsigned displayedBattle;
static _Thread_local unsigned damageDepth;
static void ObserveAbility(void *, BOOL, int);
static NSDictionary<NSNumber *, NSString *> *propertyNames;
static BOOL InitializeEnums(void) {
    @synchronized (overlay) {
        if (propertyNames) return YES;
        NSDictionary *properties = VeritasReadEnumNames(unity, VeritasTypeAbilityProperty);
        NSDictionary *attacks = VeritasReadEnumNames(unity, VeritasTypeAttackType);
        if (![properties[@(VeritasPropertyCurrentHP)] isEqual:@"CurrentHP"] ||
            ![properties[@(VeritasPropertyMaxHP)] isEqual:@"MaxHP"] ||
            ![properties[@(VeritasPropertySpeed)] isEqual:@"Speed"] ||
            ![properties[@(VeritasPropertyActionDelay)] isEqual:@"ActionDelay"] || !attacks.count) return NO;
        propertyNames = properties; VeritasNativeAttackNames = attacks;
        return YES;
    }
}

static void BattleBegin(void *mode, void *method) {
    if (!InitializeEnums()) { ((BattleRoutine)(unity + VeritasBattleBeginOriginal))(mode, method); return; }
    unsigned id = atomic_load(&activeBattle);
    if (!id) { id = ++nextBattle; atomic_store(&activeBattle, id); }
    const unsigned battleID = id;
    ((BattleRoutine)(unity + VeritasBattleBeginOriginal))(mode, method);
    unsigned (*maxWave)(void *) = (void *)(unity + VeritasGetMaxWave);
    unsigned (*maxCycle)(void *) = (void *)(unity + VeritasGetMaxCycle);
    unsigned (*stage)(void *) = (void *)(unity + VeritasGetStageID);
    unsigned waves = maxWave(mode), cycles = maxCycle(mode), stageID = stage(mode);
    dispatch_async(dispatch_get_main_queue(), ^{
        if (displayedBattle != battleID) [overlay.battle reset];
        displayedBattle = battleID;
        overlay.selectedBattle = nil;
        overlay.inBattle = YES;
        overlay.battle.maxWave = waves; overlay.battle.maxCycle = cycles; overlay.battle.stage = stageID;
        [overlay.server publish:@"OnBattleBegin" data:@{@"max_waves": @(waves), @"max_cycles": @(cycles), @"stage_id": @(stageID)}];
        [overlay requestRender];
    });
}

static void BattleEnd(void *mode, void *method) {
    unsigned finished = atomic_load(&activeBattle);
    ((BattleRoutine)(unity + VeritasBattleEndOriginal))(mode, method);
    if (!finished) return;
    unsigned expected = finished;
    atomic_compare_exchange_strong(&activeBattle, &expected, 0);
    dispatch_async(dispatch_get_main_queue(), ^{
        if (displayedBattle != finished) return;
        overlay.inBattle = NO;
        [overlay archiveBattle];
        NSDictionary *summary = overlay.battle.snapshot;
        [overlay.server publish:@"OnBattleEnd" data:@{@"avatars": summary[@"lineup"], @"turn_history": summary[@"turn_history"], @"av_history": summary[@"av_history"], @"turn_count": summary[@"turn_count"], @"total_damage": summary[@"total_damage"], @"action_value": summary[@"action_value"], @"cycle": summary[@"cycle"], @"wave": summary[@"wave"], @"stage_id": summary[@"stage_id"]}];
        [overlay requestRender];
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
    void *(*turnOwner)(void *) = (void *)(unity + VeritasGetTurnOwner);
    void *entity = turnOwner(mode);
    int (*team)(void *) = (void *)(unity + VeritasGetTeam);
    uint32_t (*runtimeID)(void *) = (void *)(unity + VeritasGetRuntimeID);
    uint32_t (*avatarID)(void *) = (void *)(unity + VeritasGetAvatarID);
    BOOL player = entity && team(entity) == 1;
    NSDictionary *owner = entity ? VeritasEntity(player ? avatarID(entity) : runtimeID(entity), player) : nil;
    dispatch_async(dispatch_get_main_queue(), ^{
        if (displayedBattle != battle) return;
        [overlay.battle beginTurnAtActionValue:actionValue wave:wave];
        [overlay.battle setTurnOwner:owner];
        [overlay requestRender];
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
    void *source = manager ? summoner(manager, attacker) : NULL;
    return source ? idForEntity(source) : 0;
}

static NSString *GameString(const char *string) {
    if (!string) return nil;
    int32_t length;
    memcpy(&length, string + VeritasStringLength, sizeof(length));
    if (length <= 0 || length > 256) return nil;
    NSString *name = [[NSString alloc] initWithCharacters:(const unichar *)(string + VeritasStringCharacters) length:(NSUInteger)length];
    return [[name stringByReplacingOccurrencesOfString:@"<ub>" withString:@""]
        stringByReplacingOccurrencesOfString:@"</ub>" withString:@""];
}

static NSString *AvatarName(uint32_t avatar) {
    const char *(*avatarName)(uint32_t) = (void *)(unity + VeritasGetAvatarName);
    return avatar ? GameString(avatarName(avatar)) : nil;
}

static NSString *SkillName(void *component, int index, int variant, int32_t *attackType, uint32_t *configID) {
    void *(*skillData)(void *, int, int) = (void *)(unity + VeritasGetSkillData);
    void *skill = skillData(component, index, variant);
    if (!skill) return nil;
    *configID = VeritasReadSkillID(unity, skill);
    void *row;
    memcpy(&row, (const char *)skill + VeritasSkillRowField, sizeof(row));
    if (!row) return nil;
    void *(*objectType)(void *) = (void *)(unity + VeritasGetObjectType);
    const char *(*typeName)(void *) = (void *)(unity + VeritasGetTypeName);
    void *type = objectType(row);
    NSString *name = type ? GameString(typeName(type)) : nil;
    uintptr_t getter = 0, typeGetter = 0;
    if ([name isEqualToString:@"AvatarSkillRowData"]) { getter = VeritasGetAvatarSkillName; typeGetter = VeritasGetAvatarSkillType; }
    else if ([name isEqualToString:@"ServantSkillRowData"]) { getter = VeritasGetServantSkillName; typeGetter = VeritasGetServantSkillType; }
    else if ([name isEqualToString:@"MonsterSkillRowData"]) { getter = VeritasGetMonsterSkillName; typeGetter = VeritasGetMonsterSkillType; }
    else if ([name isEqualToString:@"BattleEventSkillRowData"]) { getter = VeritasGetBattleEventSkillName; typeGetter = VeritasGetBattleEventSkillType; }
    if (!getter) return nil;
    *attackType = ((int32_t (*)(void *))(unity + typeGetter))(row);
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
        int32_t attackType = 0; uint32_t configID = 0;
        NSString *skill = SkillName(component, index, variant, &attackType, &configID);
        if (!skill.length) skill = [NSString stringWithFormat:@"Skill slot %d", index + 1];
        uint32_t avatar = AvatarID(entity);
        uint32_t (*runtimeOwner)(void *) = (void *)(unity + VeritasGetActualOwnerID);
        uint32_t identifier = avatar ?: runtimeOwner(entity);
        NSString *name = AvatarName(avatar);
        dispatch_async(dispatch_get_main_queue(), ^{
            if (displayedBattle != battle) return;
            [overlay.battle recordSkill:skill type:attackType configID:configID owner:identifier name:name];
            [overlay requestRender];
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
    double before = owner ? VeritasFixPoint(property(defenderAbility, VeritasPropertyCurrentHP)) : 0;
    damageDepth++;
    uintptr_t result;
    @try {
        result = ((DamageRoutine)(unity + VeritasDamageOriginal))(
            context, specification, info, attackerAbility, defenderAbility,
            attacker, defender, singleTarget, flag, method);
    } @finally { damageDepth--; }
    if (battle && atomic_load(&activeBattle) == battle) ObserveAbility(defenderAbility, NO, VeritasPropertyCurrentHP);
    if (owner && atomic_load(&activeBattle) == battle) {
        double after = VeritasFixPoint(property(defenderAbility, VeritasPropertyCurrentHP));
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
                    [overlay requestRender];
                });
            }
        }
    }
    return result;
}

typedef struct { uint64_t hasValue; int64_t value; } VeritasNullableFixPoint;
_Static_assert(sizeof(VeritasNullableFixPoint) == 16, "Nullable FixPoint ABI");
static void DirectDamage(void *component, int64_t amount, int lockStrength, void *context,
                              void *resultAmount, VeritasNullableFixPoint modifier, int integerization, void *method) {
    typedef void (*Routine)(void *, int64_t, int, void *, void *, VeritasNullableFixPoint, int, void *);
    unsigned battle = atomic_load(&activeBattle);
    int64_t (*property)(void *, int) = (void *)(unity + VeritasGetProperty);
    bool observe = false;
    if (battle && damageDepth == 0) {
        void *(*owner)(void *) = (void *)(unity + VeritasGetComponentOwner);
        int (*team)(void *) = (void *)(unity + VeritasGetTeam);
        void *target = owner(component);
        observe = target && team(target) == 2;
    }
    double before = observe ? VeritasFixPoint(property(component, VeritasPropertyCurrentHP)) : 0;
    damageDepth++;
    @try {
        ((Routine)(unity + VeritasDirectDamageOriginal))(
            component, amount, lockStrength, context, resultAmount, modifier, integerization, method);
    } @finally { damageDepth--; }
    if (battle && atomic_load(&activeBattle) == battle) ObserveAbility(component, NO, VeritasPropertyCurrentHP);
    if (observe && atomic_load(&activeBattle) == battle) {
        double loss = before - VeritasFixPoint(property(component, VeritasPropertyCurrentHP));
        if (loss > 0) dispatch_async(dispatch_get_main_queue(), ^{
            if (displayedBattle != battle) return;
            [overlay.battle recordUnattributedDirectLoss:loss];
            [overlay requestRender];
        });
    }
}

static void *ReadPointer(const void *object, unsigned offset) {
    void *value = NULL; if (object) memcpy(&value, (const char *)object + offset, sizeof(value)); return value;
}
static uint32_t ReadUInt(const void *object, unsigned offset) {
    uint32_t value = 0; if (object) memcpy(&value, (const char *)object + offset, sizeof(value)); return value;
}
static NSString *PropertyLabel(int property) {
    if (propertyNames[@(property)]) return propertyNames[@(property)];
    switch (property) {
        case VeritasPropertyCurrentHP: return @"CurrentHP";
        case VeritasPropertyMaxHP: return @"MaxHP";
        case VeritasPropertyAttack: return @"Attack";
        case VeritasPropertyDefence: return @"Defence";
        case VeritasPropertySpeed: return @"Speed";
        case VeritasPropertyActionDelay: return @"ActionDelay";
        default: return [NSString stringWithFormat:@"Property#%d", property];
    }
}
static NSDictionary *EntityIdentity(void *entity) {
    if (!entity) return nil;
    int (*team)(void *) = (void *)(unity + VeritasGetTeam);
    uint32_t (*runtimeID)(void *) = (void *)(unity + VeritasGetRuntimeID);
    BOOL player = team(entity) == 1;
    uint32_t uid = player ? AvatarID(entity) : runtimeID(entity);
    return uid ? VeritasEntity(uid, player) : nil;
}
static NSDictionary *ReadStats(void *component) {
    NSMutableDictionary *stats = [NSMutableDictionary dictionary];
    void *properties = ReadPointer(component, VeritasAbilityProperties);
    uint32_t count = ReadUInt(properties, VeritasArrayLength);
    if (count > 1024) return stats;
    for (unsigned index = 0; index < count; index++) {
        void *property = ReadPointer(properties, VeritasArrayItems + index * sizeof(void *));
        if (!property) continue;
        int64_t raw; memcpy(&raw, (const char *)property + VeritasPropertyValue, sizeof(raw));
        double value = VeritasFixPoint(raw) * (index == VeritasPropertyActionDelay ? 10 : 1);
        if (isfinite(value)) stats[PropertyLabel(index)] = @(value);
    }
    return stats;
}
static void ObserveAbility(void *component, BOOL all, int propertyID) {
    @autoreleasepool {
    unsigned battle = atomic_load(&activeBattle);
    if (!battle || !component) return;
    void *(*owner)(void *) = (void *)(unity + VeritasGetComponentOwner);
    void *entity = owner(component);
    NSDictionary *identity = EntityIdentity(entity);
    if (!identity) return;
    NSString *name = [identity[@"team"] isEqual:@"Player"] ? AvatarName([identity[@"uid"] unsignedIntValue]) : nil;
    NSDictionary *stats;
    if (all) stats = ReadStats(component);
    else {
        int64_t (*property)(void *, int) = (void *)(unity + VeritasGetProperty);
        double value = VeritasFixPoint(property(component, propertyID)) * (propertyID == VeritasPropertyActionDelay ? 10 : 1);
        stats = isfinite(value) ? @{PropertyLabel(propertyID): @(value)} : @{};
    }
    dispatch_async(dispatch_get_main_queue(), ^{
        if (displayedBattle != battle) return;
        [overlay.battle updateEntity:identity name:name stats:stats]; [overlay requestRender];
    });
    }
}
static void SetLineup(void *instance, void *configuration, void *lineup, int stage, uint32_t seed, bool flag, void *method) {
    typedef void (*Routine)(void *, void *, void *, int, uint32_t, bool, void *);
    if (!InitializeEnums()) {
        atomic_store(&activeBattle, 0);
        ((Routine)(unity + VeritasSetLineupOriginal))(instance, configuration, lineup, stage, seed, flag, method);
        dispatch_async(dispatch_get_main_queue(), ^{ [overlay log:@"Combat capture disabled: runtime enum validation failed"]; });
        return;
    }
    unsigned battle = ++nextBattle; atomic_store(&activeBattle, battle);
    @autoreleasepool {
        NSMutableArray *avatars = [NSMutableArray array];
        NSMutableDictionary *portraits = [NSMutableDictionary dictionary];
        void *team = ReadPointer(lineup, VeritasLineupLightTeam);
        uint32_t count = ReadUInt(team, VeritasArrayLength);
        if (count <= 32) for (unsigned index = 0; index < count; index++) {
            void *character = ReadPointer(team, VeritasArrayItems + index * sizeof(void *));
            uint32_t uid = ReadUInt(character, VeritasLineupCharacterID);
            if (uid) {
                [avatars addObject:@{@"id": @(uid), @"name": AvatarName(uid) ?: [@(uid) stringValue]}];
                NSString *key = [NSString stringWithFormat:@"avatars/%u", uid];
                NSData *png = VeritasCachedPortrait(key) ? nil : VeritasCaptureAvatar(unity, uid);
                if (png) portraits[key] = png;
            }
        }
        NSArray *extra = VeritasExtraLineup(unity, lineup);
        for (NSNumber *number in extra) {
            uint32_t uid = number.unsignedIntValue;
            if ([[avatars valueForKey:@"id"] containsObject:number]) continue;
            [avatars addObject:@{@"id": number, @"name": AvatarName(uid) ?: number.stringValue}];
            NSString *key = [NSString stringWithFormat:@"avatars/%u", uid];
            NSData *png = VeritasCachedPortrait(key) ? nil : VeritasCaptureAvatar(unity, uid);
            if (png) portraits[key] = png;
        }
        NSData *hp = VeritasCachedPortrait(@"properties/BaseHP") ? nil : VeritasCapturePropertyIcon(unity, @"BaseHP");
        if (hp) portraits[@"properties/BaseHP"] = hp;
        dispatch_async(dispatch_get_main_queue(), ^{
            if (!extra) [overlay log:@"ExtraTeam reflection unavailable; additional characters will appear when initialized"];
            for (NSString *key in portraits) VeritasCachePortrait(key, portraits[key]);
            displayedBattle = battle; overlay.selectedBattle = nil;
            [overlay.battle reset]; [overlay.battle setLineup:avatars]; [overlay requestRender];
        });
    }
    ((Routine)(unity + VeritasSetLineupOriginal))(instance, configuration, lineup, stage, seed, flag, method);
}
static void TurnEnd(void *component, int turn, void *method) {
    unsigned battle = atomic_load(&activeBattle);
    dispatch_async(dispatch_get_main_queue(), ^{ if (battle && displayedBattle == battle) { [overlay.battle endTurn]; [overlay requestRender]; } });
    ((void (*)(void *, int, void *))(unity + VeritasTurnEndOriginal))(component, turn, method);
}
static void WaveUpdate(void *mode, void *method) {
    ((BattleRoutine)(unity + VeritasWaveUpdateOriginal))(mode, method);
    unsigned battle = atomic_load(&activeBattle);
    unsigned (*get)(void *) = (void *)(unity + VeritasGetWave); unsigned wave = get(mode);
    dispatch_async(dispatch_get_main_queue(), ^{ if (battle && displayedBattle == battle) {
        overlay.battle.wave = wave; [overlay.server publish:@"OnUpdateWave" data:@{@"wave": @(wave)}]; [overlay requestRender];
    } });
}
static unsigned CycleUpdate(void *mode, void *method) {
    unsigned result = ((unsigned (*)(void *, void *))(unity + VeritasCycleUpdateOriginal))(mode, method);
    unsigned battle = atomic_load(&activeBattle);
    dispatch_async(dispatch_get_main_queue(), ^{ if (battle && displayedBattle == battle && overlay.battle.cycle != result) {
        overlay.battle.cycle = result; [overlay.server publish:@"OnUpdateCycle" data:@{@"cycle": @(result)}]; [overlay requestRender];
    } });
    return result;
}
static void AVReset(void *mode, void *method) {
    ((BattleRoutine)(unity + VeritasAVResetOriginal))(mode, method);
    unsigned battle = atomic_load(&activeBattle);
    int64_t (*elapsed)(void *) = (void *)(unity + VeritasGetElapsedActionDelay); double av = VeritasFixPoint(elapsed(mode)) * 10;
    dispatch_async(dispatch_get_main_queue(), ^{ if (battle && displayedBattle == battle) [overlay.battle resetAV:av]; });
}
static void DirectChangeHP(void *component, int function, int64_t amount, void *context, int strength, void *method) {
    ((void (*)(void *, int, int64_t, void *, int, void *))(unity + VeritasDirectChangeHPOriginal))(component, function, amount, context, strength, method);
    ObserveAbility(component, NO, VeritasPropertyCurrentHP);
}
static bool StatChange(void *component, int property, int function, int64_t value, void *context, void *method) {
    bool result = ((bool (*)(void *, int, int, int64_t, void *, void *))(unity + VeritasStatChangeOriginal))(component, property, function, value, context, method);
    if (property >= 0 && property < 1024) ObserveAbility(component, NO, property);
    return result;
}
static void CharacterInitialize(void *component, void *ability, void *method) {
    ((void (*)(void *, void *, void *))(unity + VeritasCharacterInitializeOriginal))(component, ability, method);
    ObserveAbility(ability, YES, 0);
}
static void EnemyInitialize(void *component, void *ability, void *method) {
    ((void (*)(void *, void *, void *))(unity + VeritasEnemyInitializeOriginal))(component, ability, method);
    unsigned battle = atomic_load(&activeBattle);
    if (!battle || !ability) return;
    void *(*owner)(void *) = (void *)(unity + VeritasGetComponentOwner);
    uint32_t (*runtimeID)(void *) = (void *)(unity + VeritasGetRuntimeID);
    unsigned (*monsterID)(void *) = (void *)(unity + VeritasGetMonsterID);
    void *(*rowFor)(void *) = (void *)(unity + VeritasGetMonsterRow);
    void *entity = owner(component), *row = rowFor(component);
    if (!entity || !row) return;
    typedef struct { int32_t hash; uint64_t hash64; } TextID;
    TextID (*nameID)(void *) = (void *)(unity + VeritasGetMonsterNameID);
    const char *(*text)(TextID, void *) = (void *)(unity + VeritasGetText);
    unsigned (*levelFor)(void *) = (void *)(unity + VeritasGetMonsterLevel);
    @autoreleasepool {
        uint32_t uid = runtimeID(entity), templateID = monsterID(component);
        NSString *name = GameString(text(nameID(row), NULL)) ?: [NSString stringWithFormat:@"Enemy %u", templateID];
        NSMutableDictionary *stats = [ReadStats(ability) mutableCopy]; stats[@"Level"] = @(levelFor(row));
        int64_t maxHP; memcpy(&maxHP, (const char *)component + VeritasEnemyDefaultHP, sizeof(maxHP));
        stats[@"MaxHP"] = @(VeritasFixPoint(maxHP));
        NSData *png = VeritasCaptureEnemy(unity, row);
        NSDictionary *enemy = @{@"id": @(templateID), @"uid": @(uid), @"name": name, @"base_stats": @{@"properties": stats}};
        dispatch_async(dispatch_get_main_queue(), ^{ if (displayedBattle == battle) { [overlay.battle initializeEnemy:enemy]; if (png) VeritasCachePortrait([NSString stringWithFormat:@"enemies/%u", templateID], png); [overlay requestRender]; } });
    }
}
static void FormationUpdate(void *component, void *method) {
    ((BattleRoutine)(unity + VeritasFormationUpdateOriginal))(component, method);
    unsigned battle = atomic_load(&activeBattle);
    if (!battle || VeritasFormationTeam(unity, component) != 2) return;
    void *list = ReadPointer(component, VeritasFormationList), *items = ReadPointer(list, VeritasListItems);
    uint32_t count = ReadUInt(list, VeritasListCount), capacity = ReadUInt(items, VeritasArrayLength);
    if (count > 64 || count > capacity) return;
    @autoreleasepool {
        NSMutableArray *enemies = [NSMutableArray array];
        for (unsigned index = 0; index < count; index++) {
            void *formation = ReadPointer(items, VeritasArrayItems + index * sizeof(void *));
            NSDictionary *entity = EntityIdentity(ReadPointer(formation, VeritasComponentOwner));
            if ([entity[@"team"] isEqual:@"Enemy"]) [enemies addObject:entity];
        }
        dispatch_async(dispatch_get_main_queue(), ^{ if (displayedBattle == battle) [overlay.battle setFormation:enemies player:NO]; });
    }
}

static BOOL MatchesSignature(uintptr_t address, const uint8_t *pattern, const uint8_t *mask, size_t length) {
    const uint8_t *actual = (const uint8_t *)address;
    for (size_t index = 0; index < length; index++) if ((actual[index] & mask[index]) != (pattern[index] & mask[index])) return NO;
    return YES;
}
static BOOL ConnectDamageHooks(void) {
    const char *suffix = "/UnityFramework.framework/UnityFramework";
    size_t length = strlen(suffix);
    for (uint32_t i = 0; i < _dyld_image_count(); i++) {
        const char *name = _dyld_get_image_name(i);
        if (!name || strlen(name) < length || strcmp(name + strlen(name) - length, suffix)) continue;
        uintptr_t image = (uintptr_t)_dyld_get_image_header(i);
        // Validate the entire contract before publishing any callback.
#define VALIDATE_HOOK(name) \
        if (memcmp((const void *)(image + Veritas##name##Entry), Veritas##name##Jump, sizeof(Veritas##name##Jump)) || \
            memcmp((const void *)(image + Veritas##name##Stub), Veritas##name##Code, sizeof(Veritas##name##Code)) || \
            atomic_load((_Atomic(uintptr_t) *)(image + Veritas##name##Slot))) return NO;
        VERITAS_HOOKS(VALIDATE_HOOK)
#undef VALIDATE_HOOK
#define VALIDATE_METHOD(name) \
        if (!MatchesSignature(image + Veritas##name, Veritas##name##Expected, Veritas##name##Mask, sizeof(Veritas##name##Expected))) return NO;
        VERITAS_METHODS(VALIDATE_METHOD)
#undef VALIDATE_METHOD
        unity = image;
#define PUBLISH_HOOK(name) \
        atomic_store_explicit((_Atomic(uintptr_t) *)(image + Veritas##name##Slot), (uintptr_t)name, memory_order_release);
        VERITAS_HOOKS(PUBLISH_HOOK)
#undef PUBLISH_HOOK
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
                @"Veritas.Opacity": @0.6, @"Veritas.TextSize": @13, @"Veritas.Theme": @"Egui",
                @"Veritas.Pie": @YES, @"Veritas.Table": @YES, @"Veritas.Legend": @YES,
                @"Veritas.characters.Visible": @YES, @"Veritas.metrics.Visible": @YES,
                @"Veritas.DateFolders": @YES, @"Veritas.BreakdownOwner": @"", @"Veritas.Shown": @YES, @"Veritas.Locale": @"en",
            }];
            [reports.server start];
            reports.battle.eventSink = ^(NSString *name, NSDictionary *data) { [overlay.server publish:name data:data]; };
            reports.shown = [NSUserDefaults.standardUserDefaults boolForKey:@"Veritas.Shown"];
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
                if ((modifiers & 0x1e0000) != 0x120000 || (!reports.gameWindow.isKeyWindow && !reports.window.isKeyWindow)) return event;
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
