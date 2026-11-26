#import <Foundation/Foundation.h>
#import "../CSV.h"

static inline NSString *VeritasCSVCell(id value) {
    return PluginCSVCell(value);
}

static inline NSArray *VeritasChartData(NSDictionary *battle) {
    NSMutableArray *rows = [NSMutableArray array];
    NSDictionary *owners = battle[@"avatars"], *names = battle[@"names"];
    double total = [battle[@"total_damage"] doubleValue], av = [battle[@"action_value"] doubleValue];
    for (NSString *key in [owners.allKeys sortedArrayUsingSelector:@selector(compare:)]) {
        double damage = [owners[key] doubleValue], peak = 0;
        NSUInteger turns = 0, first = 0, last = 0, primary = 0;
        NSMutableDictionary *uses = [NSMutableDictionary dictionary];
        for (NSDictionary *skill in battle[@"skills"]) if ([skill[@"owner"] isEqual:key]) {
            NSString *name = skill[@"skill"];
            if (!name) continue;
            uses[name] = @([uses[name] unsignedIntegerValue] + 1);
            primary = MAX(primary, [uses[name] unsignedIntegerValue]);
        }
        for (NSDictionary *turn in battle[@"turn_history"]) {
            double amount = [turn[@"damage_by_owner"][key] doubleValue];
            if (amount <= 0) continue;
            turns++; peak = MAX(peak, amount); last = [turn[@"turn"] unsignedIntegerValue]; if (!first) first = last;
        }
        [rows addObject:@{@"data_type": @"character_summary", @"character_name": names[key] ?: key, @"character_id": @(key.intValue),
            @"total_damage": @(damage), @"damage_percentage": @(total > 0 ? damage / total * 100 : 0),
            @"dpav": @(av > 0 ? damage / av : damage), @"primary_skill_usage_count": @(primary), @"turns_taken": @(turns),
            @"average_damage_per_turn": @(turns > 0 ? damage / turns : 0), @"max_single_turn_damage": @(peak),
            @"first_turn_number": @(first), @"last_turn_number": @(last)}];
    }
    double cumulative = 0; NSUInteger order = 0;
    NSMutableDictionary *characterCumulative = [NSMutableDictionary dictionary];
    for (NSDictionary *skill in battle[@"skills"]) {
        NSString *key = skill[@"owner"] ?: @""; double damage = [skill[@"total_damage"] doubleValue];
        cumulative += damage; characterCumulative[key] = @([characterCumulative[key] doubleValue] + damage);
        [rows addObject:@{@"data_type": @"skill_detail", @"character_name": names[key] ?: key, @"character_id": @([key intValue]),
            @"turn_order": @(++order), @"turn_battle_id": skill[@"turn"] ?: @0, @"wave": skill[@"wave"] ?: @0, @"cycle": skill[@"cycle"] ?: @0,
            @"action_value": skill[@"action_value"] ?: @0, @"skill_name": skill[@"skill"] ?: @"", @"skill_type": skill[@"skill_type"] ?: @"Unknown",
            @"skill_type_name": skill[@"skill_type"] ?: @"Unknown", @"skill_damage": @(damage),
            @"cumulative_damage": @(cumulative), @"cumulative_character_damage": characterCumulative[key] ?: @0,
            @"skill_damage_percentage": @(total > 0 ? damage / total * 100 : 0)}];
    }
    return rows;
}
static inline NSString *VeritasCSV(NSDictionary *battle) {
    NSArray *columns = @[@"data_type", @"character_name", @"character_id", @"total_damage", @"damage_percentage", @"dpav",
        @"primary_skill_usage_count", @"turns_taken", @"average_damage_per_turn", @"max_single_turn_damage", @"first_turn_number",
        @"last_turn_number", @"turn_order", @"turn_battle_id", @"wave", @"cycle", @"action_value", @"skill_name", @"skill_type",
        @"skill_type_name", @"skill_damage", @"cumulative_damage", @"cumulative_character_damage", @"skill_damage_percentage"];
    NSMutableString *csv = [[columns componentsJoinedByString:@","] mutableCopy]; [csv appendString:@"\r\n"];
    for (NSDictionary *row in VeritasChartData(battle)) {
        NSMutableArray *cells = [NSMutableArray array];
        for (NSString *column in columns) [cells addObject:VeritasCSVCell(row[column])];
        [csv appendFormat:@"%@\r\n", [cells componentsJoinedByString:@","]];
    }
    return csv;
}
static inline NSArray *VeritasStatsHistory(NSArray *history) {
    NSMutableArray *rows = [NSMutableArray array];
    for (NSDictionary *record in history) {
        [rows addObject:@{@"stats": record[@"stats"] ?: @{}, @"turnBattleId": record[@"turn_battle_id"] ?: @0}];
    }
    return rows;
}
static inline NSDictionary *VeritasExportData(NSDictionary *snapshot) {
    NSMutableArray *lineup = [NSMutableArray array], *turns = [NSMutableArray array], *skills = [NSMutableArray array];
    NSDictionary *entities = snapshot[@"entities"];
    NSMutableDictionary *avatarDetail = [NSMutableDictionary dictionary], *enemyDetail = [NSMutableDictionary dictionary];
    for (NSDictionary *avatar in snapshot[@"lineup"]) {
        NSNumber *uid = avatar[@"id"];
        if (!uid) continue;
        NSDictionary *record = entities[[NSString stringWithFormat:@"Player:%@", uid]];
        [lineup addObject:@{@"avatarId": uid, @"isDie": record[@"is_die"] ?: @NO}];
        avatarDetail[uid.stringValue] = @{@"id": uid, @"isDie": record[@"is_die"] ?: @NO,
            @"killer_uid": [record[@"killer"] isKindOfClass:NSDictionary.class] ? (record[@"killer"][@"uid"] ?: @(-1)) : @(-1),
            @"stats": record[@"stats"] ?: @{}, @"statsHistory": VeritasStatsHistory(record[@"stats_history"])};
    }
    [turns addObject:@{@"avatarId": @(-1), @"actionValue": @0, @"waveIndex": snapshot[@"wave"] ?: @0, @"cycleIndex": snapshot[@"max_cycle"] ?: @0}];
    for (NSDictionary *turn in snapshot[@"entity_turn_history"]) {
        NSDictionary *entity = turn[@"entity"];
        if (![entity isKindOfClass:NSDictionary.class] || !entity[@"uid"]) continue;
        [turns addObject:@{@"avatarId": entity[@"uid"], @"actionValue": turn[@"action_value"] ?: @0,
            @"waveIndex": turn[@"wave"] ?: @0, @"cycleIndex": turn[@"cycle"] ?: @0}];
    }
    for (NSDictionary *skill in snapshot[@"skills"]) {
        [skills addObject:@{@"avatarId": @([skill[@"owner"] intValue]), @"damageDetail": skill[@"damage_detail"] ?: @[],
            @"totalDamage": skill[@"total_damage"] ?: @0, @"skillType": skill[@"skill_type"] ?: @"Unknown", @"skillName": skill[@"skill"] ?: @"",
            @"turnBattleId": skill[@"turn"] ?: @0}];
    }
    NSUInteger index = 0;
    for (NSString *uid in [[snapshot[@"enemies"] allKeys] sortedArrayUsingSelector:@selector(compare:)]) {
        NSDictionary *enemy = snapshot[@"enemies"][uid], *record = entities[[@"Enemy:" stringByAppendingString:uid]];
        enemyDetail[uid] = @{@"id": enemy[@"id"] ?: @0, @"name": enemy[@"name"] ?: uid, @"stats": record[@"stats"] ?: @{},
            @"maxHP": enemy[@"base_stats"][@"properties"][@"MaxHP"] ?: @0, @"level": enemy[@"base_stats"][@"properties"][@"Level"] ?: @0,
            @"statsHistory": VeritasStatsHistory(record[@"stats_history"]), @"isDie": record[@"is_die"] ?: @NO,
            @"killer_uid": [record[@"killer"] isKindOfClass:NSDictionary.class] ? (record[@"killer"][@"uid"] ?: @(-1)) : @(-1),
            @"positionIndex": @(index++), @"waveIndex": snapshot[@"wave"] ?: @0};
    }
    return @{@"lineup": lineup, @"turnHistory": turns, @"skillHistory": skills, @"dataAvatar": @[],
        @"totalAV": snapshot[@"action_value"] ?: @0, @"totalDamage": snapshot[@"total_damage"] ?: @0,
        @"damagePerAV": snapshot[@"damage_per_av"] ?: @0, @"cycleIndex": snapshot[@"cycle"] ?: @0,
        @"waveIndex": snapshot[@"wave"] ?: @0, @"maxWave": snapshot[@"max_wave"] ?: @0, @"maxCycle": snapshot[@"max_cycle"] ?: @0,
        @"avatarDetail": avatarDetail, @"enemyDetail": enemyDetail, @"version": @"0.2.58", @"_playcover": snapshot ?: @{}};
}

static inline NSURL *VeritasExportDirectory(void) {
    NSURL *documents = [[NSFileManager defaultManager] URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    NSString *custom = [[NSUserDefaults.standardUserDefaults stringForKey:@"Veritas.ExportPath"] stringByExpandingTildeInPath];
    NSURL *directory = custom.length ? [NSURL fileURLWithPath:custom isDirectory:YES] :
        [documents URLByAppendingPathComponent:@"Veritas/Exports" isDirectory:YES];
    if ([NSUserDefaults.standardUserDefaults boolForKey:@"Veritas.DateFolders"]) {
        NSDateFormatter *formatter = [NSDateFormatter new]; formatter.dateFormat = @"yyyy-MM-dd";
        directory = [directory URLByAppendingPathComponent:[formatter stringFromDate:NSDate.date] isDirectory:YES];
    }
    return directory;
}

static inline NSURL *VeritasWriteExport(NSDictionary *battle, BOOL csv, NSError **error) {
    NSString *custom = [[NSUserDefaults.standardUserDefaults stringForKey:@"Veritas.ExportPath"] stringByExpandingTildeInPath];
    if (custom.length && !custom.isAbsolutePath) {
        if (error) *error = [NSError errorWithDomain:@"Veritas" code:1 userInfo:@{NSLocalizedDescriptionKey: @"Export folder must be an absolute path or start with ~"}];
        return nil;
    }
    NSURL *directory = VeritasExportDirectory();
    if (![NSFileManager.defaultManager createDirectoryAtURL:directory withIntermediateDirectories:YES attributes:nil error:error]) return nil;
    NSString *filename = [NSString stringWithFormat:@"battle-%@.%@", NSUUID.UUID.UUIDString, csv ? @"csv" : @"json"];
    NSURL *url = [directory URLByAppendingPathComponent:filename];
    NSData *data = csv ? [VeritasCSV(battle) dataUsingEncoding:NSUTF8StringEncoding] :
        [NSJSONSerialization dataWithJSONObject:VeritasExportData(battle) options:NSJSONWritingPrettyPrinted error:error];
    return data && [data writeToURL:url options:NSDataWritingAtomic error:error] ? url : nil;
}
