#import "Telemetry.h"
#include <assert.h>

int main(void) {
    @autoreleasepool {
        const int64_t fields[] = {INT64_C(100) << 33, (INT64_C(20) << 26) | 1, 0, 0};
        assert(VeritasFixPoint(fields[0]) == 100);
        assert(VeritasFixPoint(fields[1]) == 20);
        double overkill;
        assert(VeritasDamageTotal(fields, 200, 100, &overkill) == 120 && overkill == 0);
        assert(VeritasDamageTotal(fields, 25, 0, &overkill) == 45 && overkill == 75);
        VeritasBattle *battle = [VeritasBattle new];
        [battle beginTurnAtActionValue:15 wave:1];
        [battle record:50 overkill:0 owner:1001 name:@"Cipher"];
        [battle record:25 overkill:10 owner:1002 name:@"Hyacine"];
        [battle beginTurnAtActionValue:30 wave:1];
        [battle record:10 overkill:0 owner:1001 name:nil];
        [battle recordAttackType:1 damage:30 owner:1001];
        [battle recordAttackType:1 damage:20 owner:1001];
        [battle recordAttackType:6 damage:10 owner:1001];
        [battle recordAttackType:99 damage:25 owner:1002];
        [battle recordSkill:@"Test skill" owner:1001 name:@"Cipher"];
        assert([battle.series[@"attackDamage"][@"1001"][@"Basic ATK"] isEqual:@50]);
        assert([battle.series[@"attackDamage"][@"1001"][@"Follow-up"] isEqual:@10]);
        assert([battle.series[@"attackDamage"][@"1002"][@"Attack type 99"] isEqual:@25]);
        assert([battle.series[@"skills"][0][@"skill"] isEqual:@"Test skill"]);
        assert([battle.series[@"skills"][0][@"turn"] isEqual:@2]);
        [battle recordUnattributedDirectLoss:8];
        [battle recordUnattributedDirectLoss:-1];
        assert(battle.unattributedDirectLoss == 8);
        assert(battle.hits == 3 && battle.total == 85);
        assert(([battle.series[@"history"] isEqual:@[@0, @50, @75, @85]]));
        assert([battle.series[@"avatars"][@"1001"] isEqual:@60]);
        assert([battle.series[@"names"][@"1001"] isEqual:@"Cipher"]);
        assert(([battle.series[@"turns"] isEqual:@[@0, @75, @10]]));
        assert(battle.overkill == 10 && battle.turn == 2 && battle.wave == 1 && battle.actionValue == 30);
        [battle beginTurnAtActionValue:6 wave:2];
        assert(battle.actionValue == 36 && battle.wave == 2);
        for (unsigned i = 0; i < 300; i++) [battle record:1 overkill:0 owner:1001 name:nil];
        assert([battle.series[@"history"] count] == 241);
        assert(battle.total == 385);
        [battle reset];
        assert(battle.hits == 0 && battle.total == 0);
        assert([battle.series[@"skills"] count] == 0 && [battle.series[@"attackDamage"] count] == 0);
    }
}
