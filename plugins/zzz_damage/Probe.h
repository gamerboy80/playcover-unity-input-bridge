#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include "ZZZDamageProfile.h"

typedef struct {
    uint32_t target, source, kind;
    float amount;
    bool hidden, suppressed;
} ProbeEvent;

typedef struct {
    uint32_t id, kind;
    bool observed, matches;
} ProbeEntity;

// shortcut: training captures establish kinds 1→2 only, expand after checking other entity kinds.
static inline bool ProbeCountsDamage(ProbeEvent event, ProbeEntity source, ProbeEntity target) {
    return isfinite(event.amount) && event.amount > 0 && !event.hidden && !event.suppressed &&
           (event.kind == 0 || event.kind == 2) && event.source && event.target &&
           source.observed && source.matches && source.id == event.source && source.kind == 1 &&
           target.observed && target.matches && target.id == event.target && target.kind == 2;
}

static inline bool ProbeMeterShortcut(uint64_t modifiers) {
    const uint64_t shift = 1ULL << 17, control = 1ULL << 18;
    const uint64_t option = 1ULL << 19, command = 1ULL << 20;
    // Command passes the input bridge; no Shift avoids screenshot shortcuts.
    return (modifiers & (shift | control | option | command)) == (control | command);
}

static inline int ProbePhaseForKey(uint64_t modifiers, unsigned keyCode) {
    if (!ProbeMeterShortcut(modifiers)) return -1;
    static const unsigned digits[] = {29, 18, 19, 20, 21};
    for (unsigned phase = 0; phase < sizeof(digits) / sizeof(digits[0]); phase++) {
        if (keyCode == digits[phase]) return (int)phase;
    }
    return -1;
}

static inline uint32_t ProbeU32(const void *base, unsigned offset) {
    uint32_t value;
    memcpy(&value, (const char *)base + offset, sizeof(value));
    return value;
}

static inline ProbeEvent ProbeDecode(const void *payload) {
    ProbeEvent event = {
        .target = ProbeU32(payload, ProbeEventTarget),
        .source = ProbeU32(payload, ProbeEventSource),
        .kind = ProbeU32(payload, ProbeEventKind),
        .hidden = ((const uint8_t *)payload)[ProbeEventHidden] != 0,
        .suppressed = ((const uint8_t *)payload)[ProbeEventSuppress] != 0,
    };
    memcpy(&event.amount, (const char *)payload + ProbeEventAmount, sizeof(event.amount));
    return event;
}

static inline ProbeEntity ProbeResolve(const void *entity, uint32_t requested) {
    ProbeEntity result = {.observed = true};
    if (entity) {
        result.id = ProbeU32(entity, ProbeEntityID);
        result.kind = ProbeU32(entity, ProbeEntityType);
        result.matches = requested != 0 && result.id == requested;
    }
    return result;
}
