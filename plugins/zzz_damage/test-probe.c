#include <assert.h>
#include "Meter.h"

int main(void) {
    const unsigned keys[] = {29, 18, 19, 20, 21};
    for (unsigned phase = 0; phase < 5; phase++) {
        assert(ProbePhaseForKey((1ULL << 18) | (1ULL << 20), keys[phase]) == (int)phase);
        assert(ProbePhaseForKey((1ULL << 18) | (1ULL << 20) | (1ULL << 16), keys[phase]) == (int)phase);
        assert(ProbePhaseForKey((1ULL << 18) | (1ULL << 19), keys[phase]) == -1);
        assert(ProbePhaseForKey((1ULL << 17) | (1ULL << 20), keys[phase]) == -1);
        assert(ProbePhaseForKey(0, keys[phase]) == -1);
    }
    assert(ProbePhaseForKey((1ULL << 18) | (1ULL << 20), 22) == -1);
    uint8_t event[106] = {0};
    uint32_t target = 123, source = 456;
    float amount = 1234.5f;
    memcpy(event, &target, 4);
    memcpy(event + 4, &source, 4);
    memcpy(event + 0x34, &amount, 4);
    event[0x38] = 2;
    event[0x3c] = 1;
    ProbeEvent decoded = ProbeDecode(event);
    assert(decoded.target == 123 && decoded.source == 456);
    assert(decoded.amount == 1234.5f && decoded.kind == 2);
    assert(decoded.hidden && !decoded.suppressed);
    uint8_t entity[0x54] = {0};
    memcpy(entity + 0x38, &source, 4);
    entity[0x50] = 7;
    ProbeEntity resolved = ProbeResolve(entity, 456);
    assert(resolved.observed && resolved.matches && resolved.kind == 7);
    assert(!ProbeResolve(entity, 123).matches);
    assert(!ProbeResolve(NULL, 456).matches);
    source = 0;
    memcpy(entity + 0x38, &source, 4);
    assert(!ProbeResolve(entity, 0).matches);
    amount = NAN;
    memcpy(event + 0x34, &amount, 4);
    assert(!isfinite(ProbeDecode(event).amount));

    ProbeEvent hit = {.source = 1, .target = 2, .amount = 100, .kind = 2};
    ProbeEntity actor = {.id = 1, .kind = 1, .observed = true, .matches = true};
    ProbeEntity enemy = {.id = 2, .kind = 2, .observed = true, .matches = true};
    assert(ProbeCountsDamage(hit, actor, enemy));
    assert(!ProbeCountsDamage(hit, enemy, actor));
    assert(!ProbeCountsDamage(hit, (ProbeEntity){0}, enemy));
    assert(!ProbeCountsDamage(hit, actor, (ProbeEntity){0}));
    hit.suppressed = true;
    assert(!ProbeCountsDamage(hit, actor, enemy));

    DamageMeter meter = {.resetAt = 10};
    MeterRecord(&meter, (MeterSource){.id = 9, .damage = 200}, 9);
    MeterRecord(&meter, (MeterSource){.id = 1, .damage = 100}, 12);
    MeterRecord(&meter, (MeterSource){.id = 2, .damage = 50}, 11);
    MeterRecord(&meter, (MeterSource){.id = 1, .damage = 25}, 13);
    assert(meter.count == 2 && meter.total == 175 && meter.latestSource.id == 1);
    assert(meter.first == 11 && meter.last == 13);
    assert(meter.sources[0].id == 1 && meter.sources[0].damage == 125);
    assert(meter.sources[1].id == 2 && meter.sources[1].damage == 50);
    MeterSource named = {.id = 1, .damage = 30};
    MeterCopyName(named.name, u"Alice(Clone)", 12);
    assert(!memcmp(named.name, u"Alice", 6 * sizeof(uint16_t)));
    MeterRecord(&meter, named, 14);
    named.name[0] = 'B';
    MeterRecord(&meter, named, 15);
    assert(meter.count == 4 && meter.total == 235);
    assert(meter.sources[2].name[0] == 'A' && meter.latestSource.name[0] == 'B');
    MeterSource runtime = {.id = 220};
    MeterCopyName(runtime.name, u"Avatar:220", 10);
    MeterDropRuntimeName(&runtime);
    assert(!runtime.name[0]);
    MeterCopyName(runtime.name, u"Avatar: 221", 11);
    MeterDropRuntimeName(&runtime);
    assert(runtime.name[0] == 'A');

    DamageMeter roster = {0};
    MeterRecord(&roster, (MeterSource){.id = 220, .avatarID = 1401, .damage = 10}, 1);
    MeterRecord(&roster, (MeterSource){.id = 6, .avatarID = 1401, .damage = 20}, 2);
    MeterRecord(&roster, (MeterSource){.id = 220, .avatarID = 1511, .damage = 40}, 3);
    MeterRecord(&roster, (MeterSource){.id = 220, .damage = 80}, 4);
    assert(roster.count == 3 && roster.total == 150);
    assert(roster.sources[0].avatarID == 1401 && roster.sources[0].damage == 30);
    assert(roster.sources[1].avatarID == 1511 && roster.sources[1].damage == 40);
    assert(roster.sources[2].avatarID == 0 && roster.sources[2].damage == 80);
}
