#import "Telemetry.h"
#import "Export.h"
#include <assert.h>

int main(void) {
    @autoreleasepool {
        const int64_t fields[] = {INT64_C(100) << 33, (INT64_C(20) << 26) | 1, 0, 0};
        assert(VeritasFixPoint(fields[0]) == 100 && VeritasFixPoint(fields[1]) == 20);
        double overkill;
        assert(VeritasDamageTotal(fields, 200, 100, &overkill) == 120 && overkill == 0);
        assert(VeritasDamageTotal(fields, 25, 0, &overkill) == 120 && overkill == 75);
        assert([VeritasAttackType(9) isEqual:@"Follow-Up"] && [VeritasAttackType(15) isEqual:@"Assist"]);
        VeritasNativeAttackNames = @{@99: @"DOT", @100: @"NewCategory"};
        assert([VeritasAttackType(99) isEqual:@"DoT"] && [VeritasAttackType(100) isEqual:@"NewCategory"]);
        VeritasNativeAttackNames = nil;
        VeritasBattle *battle = [VeritasBattle new];
        NSMutableArray *packets = [NSMutableArray array];
        battle.eventSink = ^(NSString *name, NSDictionary *data) { [packets addObject:@{@"type": name, @"data": data}]; };
        [battle setLineup:@[@{@"id": @1001, @"name": @"Cipher"}, @{@"id": @1002, @"name": @"Hyacine"}]];
        [battle beginTurnAtActionValue:15 wave:1]; [battle setTurnOwner:VeritasEntity(1001, YES)];
        [battle recordSkill:@"Test, \"skill\"" type:2 configID:12345 owner:1001 name:@"Cipher"];
        [battle record:50 overkill:0 owner:1001 name:@"Cipher"];
        [battle recordAttackType:1 damage:50 owner:1001];
        [battle record:25 overkill:10 owner:1002 name:@"Hyacine"];
        [battle recordAttackType:99 damage:25 owner:1002];
        NSDictionary *packet = packets.lastObject;
        assert([packet[@"type"] isEqual:@"OnDamage"] && [packet[@"data"][@"overkill_damage"] isEqual:@10]);
        [battle beginTurnAtActionValue:30 wave:1]; [battle setTurnOwner:VeritasEntity(9, NO)];
        [battle record:10 overkill:0 owner:1001 name:nil]; [battle recordAttackType:9 damage:10 owner:1001];
        [battle endTurn]; [battle endTurn];
        assert([battle.series[@"attackDamage"][@"1001"][@"Basic"] isEqual:@50]);
        assert([battle.series[@"attackDamage"][@"1001"][@"Follow-Up"] isEqual:@10]);
        assert([battle.series[@"attackDamage"][@"1002"][@"Attack type 99"] isEqual:@25]);
        assert([battle.series[@"skills"][0][@"total_damage"] isEqual:@60]);
        assert([battle.series[@"skills"][0][@"turn"] isEqual:@1]);
        assert([battle.series[@"skills"][0][@"skill_config_id"] isEqual:@12345]);
        assert([battle.series[@"turn_history"] count] == 2);
        assert([battle.series[@"turn_history"][0][@"total_damage"] isEqual:@75]);
        [battle beginTurnAtActionValue:30 wave:1];
        [battle record:15 overkill:0 owner:1002 name:nil]; [battle endTurn];
        assert([battle.series[@"av_history"] count] == 2);
        assert([battle.series[@"av_history"][1][@"total_damage"] isEqual:@25]);
        assert([battle.series[@"av_history"][1][@"avatars_turn_damage"][1] isEqual:@15]);
        [battle recordUnattributedDirectLoss:8]; [battle recordUnattributedDirectLoss:-1];
        assert(battle.unattributedDirectLoss == 8 && battle.total == 100 && battle.overkill == 10);
        [battle beginTurnAtActionValue:6 wave:2]; assert(battle.actionValue == 36);
        [battle resetAV:0]; [battle beginTurnAtActionValue:5 wave:2];
        assert(battle.actionValue == 41 && battle.resetActionValue == 36);
        [battle resetAV:7]; assert(battle.actionValue == 43 && battle.resetActionValue == 43);
        [battle beginTurnAtActionValue:8 wave:2]; assert(battle.actionValue == 44);
        [battle updateEntity:VeritasEntity(1001, YES) name:@"Cipher" stats:@{@"CurrentHP": @50, @"Speed": @130}];
        [battle updateEntity:VeritasEntity(1001, YES) name:nil stats:@{@"CurrentHP": @50}];
        assert([battle.series[@"entities"][@"Player:1001"][@"stats_history"] count] == 1);
        [battle initializeEnemy:@{@"id": @1, @"uid": @9, @"name": @"Test enemy", @"base_stats": @{@"properties": @{@"CurrentHP": @100, @"MaxHP": @200}}}];
        [battle setFormation:@[VeritasEntity(9, NO)] player:NO];
        assert([battle.series[@"enemy_formation_known"] boolValue]);
        [battle defeat:VeritasEntity(9, NO) killer:VeritasEntity(1001, YES)];
        NSDictionary *saved = battle.snapshot;
        [battle updateEntity:VeritasEntity(1001, YES) name:nil stats:@{@"CurrentHP": @25}];
        assert([saved[@"entities"][@"Player:1001"][@"stats"][@"CurrentHP"] isEqual:@50]);
        assert([VeritasCSV(saved) containsString:@"\"Test, \"\"skill\"\"\""]);
        assert([VeritasCSVCell(@"=1+1") isEqual:@"\"'=1+1\""]);
        assert([VeritasExportData(saved)[@"totalDamage"] isEqual:@100]);
        assert([VeritasExportData(saved)[@"lineup"][0][@"avatarId"] isEqual:@1001]);
        assert([VeritasChartData(saved)[0][@"turns_taken"] isEqual:@2]);
        assert([VeritasExportData(saved)[@"skillHistory"][0][@"skillType"] isEqual:@"BPSkill"]);
        assert([NSJSONSerialization isValidJSONObject:VeritasExportData(saved)]);
        for (unsigned i = 0; i < 300; i++) [battle record:1 overkill:0 owner:1001 name:nil];
        assert([battle.series[@"history"] count] == 305 && battle.total == 400);
        [battle record:NAN overkill:0 owner:1001 name:nil]; assert(battle.total == 400);
        NSUserDefaults *prefs = NSUserDefaults.standardUserDefaults;
        [prefs setVolatileDomain:@{@"Veritas.ExportPath": @"relative/path"} forName:NSArgumentDomain];
        NSError *error = nil;
        assert(!VeritasWriteExport(saved, NO, &error) && error);
        NSString *folder = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
        [prefs setVolatileDomain:@{@"Veritas.ExportPath": folder} forName:NSArgumentDomain];
        NSURL *json = VeritasWriteExport(saved, NO, &error), *csv = VeritasWriteExport(saved, YES, &error);
        assert(json && csv);
        NSDictionary *exported = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfURL:json] options:0 error:NULL];
        assert([exported[@"totalDamage"] isEqual:@100]);
        assert([[[NSString alloc] initWithContentsOfURL:csv encoding:NSUTF8StringEncoding error:NULL] hasPrefix:@"data_type,"]);
        assert([NSFileManager.defaultManager removeItemAtPath:folder error:NULL]);
        [prefs setVolatileDomain:@{} forName:NSArgumentDomain];
        [battle reset]; assert(battle.total == 0 && [battle.series[@"skills"] count] == 0);
        assert([saved[@"total_damage"] isEqual:@100]);
        NSDictionary *partial = @{@"avatars": @{@"99": @40}, @"names": @{},
            @"skills": @[@{@"total_damage": @15}],
            @"lineup": @[@{@"id": @99}],
            @"entities": @{@"Player:99": @{@"stats_history": @[@{}]}},
            @"enemies": @{@"7": @{@"id": @10}}};
        assert([VeritasChartData(partial) count] == 2);
        assert([VeritasCSV(partial) containsString:@"\"0\",\"\""]);
        assert([NSJSONSerialization isValidJSONObject:VeritasExportData(partial)]);
    }
}
