#pragma once
#include "Probe.h"

enum { MeterNameCapacity = 65 };

typedef struct {
    uint32_t id, avatarID;
    double damage;
    uint16_t name[MeterNameCapacity];
} MeterSource;

typedef struct {
    double resetAt, first, last, total, other;
    unsigned count;
    bool frozen;
    MeterSource latestSource;
    MeterSource sources[64];
} DamageMeter;

static inline void MeterReset(DamageMeter *meter, double time) {
    *meter = (DamageMeter){.resetAt = time, .frozen = meter->frozen};
}

static inline void MeterFreeze(DamageMeter *meter, double gameTime) {
    if (meter->frozen) return;
    if (meter->total) meter->last = fmax(meter->last, gameTime);
    meter->frozen = true;
}

static inline double MeterElapsed(const DamageMeter *meter, double gameTime) {
    if (!meter->total) return 0;
    double end = meter->frozen ? meter->last : fmax(meter->last, gameTime);
    return fmax(0, end - meter->first);
}

static inline bool MeterIsAgentName(const uint16_t *name, size_t length) {
    if (!length || length >= MeterNameCapacity) return false;
    for (size_t i = 0; i < length; ++i) {
        if (name[i] < 32 || (name[i] >= 127 && name[i] <= 159) ||
            name[i] == '/' || name[i] == '\\' || name[i] == '_') return false;
    }
    return true;
}

static inline void MeterRecord(DamageMeter *meter, MeterSource hit, double realTime, double time) {
    if (meter->frozen || realTime < meter->resetAt) return;
    if (!meter->total || time < meter->first) meter->first = time;
    if (!meter->total || time >= meter->last) {
        meter->last = time;
        meter->latestSource = hit;
    }
    meter->total += hit.damage;
    for (unsigned i = 0; i < meter->count; ++i) {
        MeterSource *source = &meter->sources[i];
        bool same = hit.avatarID ? source->avatarID == hit.avatarID :
            !source->avatarID && source->id == hit.id && !memcmp(source->name, hit.name, sizeof(hit.name));
        if (same) {
            source->damage += hit.damage;
            return;
        }
    }
    // shortcut: group new IDs beyond storage capacity, add encounter tracking if long runs need it.
    if (meter->count == sizeof(meter->sources) / sizeof(meter->sources[0])) meter->other += hit.damage;
    else meter->sources[meter->count++] = hit;
}

static inline double MeterAdvanceClock(double time, float delta) {
    return isfinite(delta) && delta >= 0 ? time + delta : time;
}

static inline void MeterCopyName(uint16_t *out, const uint16_t *name, size_t length) {
    static const uint16_t clone[] = {'(', 'C', 'l', 'o', 'n', 'e', ')'};
    size_t suffix = sizeof(clone) / sizeof(clone[0]);
    if (length >= suffix && !memcmp(name + length - suffix, clone, sizeof(clone))) length -= suffix;
    while (length && name[length - 1] == ' ') --length;
    if (!length || length >= MeterNameCapacity) return;
    for (size_t i = 0; i < length; ++i) {
        if (name[i] < 32 || (name[i] >= 127 && name[i] <= 159)) return;
    }
    memcpy(out, name, length * sizeof(*out));
}

static inline void MeterDropRuntimeName(MeterSource *source) {
    static const uint16_t prefix[] = {'A','v','a','t','a','r',':'};
    if (memcmp(source->name, prefix, sizeof(prefix))) return;
    size_t i = sizeof(prefix) / sizeof(prefix[0]);
    while (source->name[i] == ' ') ++i;
    uint64_t id = 0;
    size_t start = i;
    for (; i < MeterNameCapacity && source->name[i] >= '0' && source->name[i] <= '9'; ++i) {
        id = id * 10 + (source->name[i] - '0');
        if (id > UINT32_MAX) return;
    }
    if (i > start && i < MeterNameCapacity && !source->name[i] && id == source->id)
        memset(source->name, 0, sizeof(source->name));
}
