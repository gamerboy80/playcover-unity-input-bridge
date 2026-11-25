#import <UIKit/UIKit.h>
#import "Assets.h"
#import "VeritasProfile.h"
#include <cstring>

static void *PointerAt(const void *object, unsigned offset) {
    void *value = nullptr; if (object) memcpy(&value, (const char *)object + offset, sizeof(value)); return value;
}
static uint32_t CountAt(const void *object, unsigned offset) {
    uint32_t value = 0; if (object) memcpy(&value, (const char *)object + offset, sizeof(value)); return value;
}
static NSString *ManagedString(const void *object) {
    uint32_t length = CountAt(object, VeritasStringLength);
    if (!length || length > 512) return nil;
    return [[NSString alloc] initWithCharacters:(const unichar *)((const char *)object + VeritasStringCharacters) length:length];
}
static void *RuntimeType(uintptr_t image, unsigned index) {
    void *klass = ((void *(*)(int))(image + VeritasResolveClass))((int)index);
    return klass ? ((void *(*)(void *))(image + VeritasTypeObject))((char *)klass + VeritasClassType) : nullptr;
}
NSDictionary<NSNumber *, NSString *> *VeritasReadEnumNames(uintptr_t image, unsigned typeIndex) {
    try {
        void *type = RuntimeType(image, typeIndex);
        if (!type) return nil;
        void *names = ((void *(*)(void *, void *))(image + VeritasEnumNames))(type, nullptr);
        void *values = ((void *(*)(void *, void *))(image + VeritasEnumValues))(type, nullptr);
        uint32_t count = CountAt(names, VeritasArrayLength);
        if (!names || !values || !count || count > 2048 || count != CountAt(values, VeritasArrayLength)) return nil;
        NSMutableDictionary *result = [NSMutableDictionary dictionaryWithCapacity:count];
        for (unsigned index = 0; index < count; index++) {
            NSString *name = ManagedString(PointerAt(names, VeritasArrayItems + index * sizeof(void *)));
            int32_t value; memcpy(&value, (char *)values + VeritasArrayItems + index * sizeof(value), sizeof(value));
            if (!name) return nil;
            result[@(value)] = name;
        }
        return result;
    } catch (...) { return nil; }
}
NSData *VeritasCaptureSprite(uintptr_t image, void *path) {
    if (!path) return nil;
    void *temporary = nullptr, *previous = nullptr, *readable = nullptr;
    bool changed = false;
    NSData *png = nil;
    auto capture = [&]() -> NSData * {
        void *type = RuntimeType(image, VeritasTypeSprite);
        if (!type) return nil;
        void *sprite = ((void *(*)(void *, void *, bool, void *))(image + VeritasLoadSprite))(path, type, false, nullptr);
        void *texture = sprite ? ((void *(*)(void *, void *))(image + VeritasSpriteTexture))(sprite, nullptr) : nullptr;
        if (!texture) return nil;
        int width = ((int (*)(void *))(image + VeritasTextureWidth))(texture);
        int height = ((int (*)(void *))(image + VeritasTextureHeight))(texture);
        if (width <= 0 || height <= 0 || width > 2048 || height > 2048) return nil;
        NSNumber *format = [[VeritasReadEnumNames(image, VeritasTypeRenderTextureFormat) allKeysForObject:@"Default"] firstObject];
        NSNumber *readWrite = [[VeritasReadEnumNames(image, VeritasTypeRenderTextureReadWrite) allKeysForObject:@"Linear"] firstObject];
        if (!format || !readWrite) return nil;
        previous = ((void *(*)())(image + VeritasActiveTexture))();
        temporary = ((void *(*)(int, int, int, int, int))(image + VeritasTemporaryTexture))(width, height, 0, format.intValue, readWrite.intValue);
        if (!temporary) return nil;
        changed = true;
        ((void (*)(void *, void *))(image + VeritasBlitTexture))(texture, temporary);
        ((void (*)(void *))(image + VeritasSetActiveTexture))(temporary); changed = true;
        void *textureClass = ((void *(*)(int))(image + VeritasResolveClass))(VeritasTypeTexture2D);
        if (!textureClass) return nil;
        readable = ((void *(*)(void *))(image + VeritasAllocateObject))(textureClass);
        if (!readable) return nil;
        ((void (*)(void *, int, int))(image + VeritasTextureConstructor))(readable, width, height);
        struct Rect { float x, y, width, height; };
        ((void (*)(void *, Rect, int, int))(image + VeritasReadPixels))(readable, {0, 0, (float)width, (float)height}, 0, 0);
        ((void (*)(void *))(image + VeritasApplyTexture))(readable);
        void *bytes = ((void *(*)(void *))(image + VeritasEncodePNG))(readable);
        uint32_t length = CountAt(bytes, VeritasArrayLength);
        return length && length <= 16 * 1024 * 1024 ? [NSData dataWithBytes:(char *)bytes + VeritasArrayItems length:length] : nil;
    };
    try { png = capture(); } catch (...) { png = nil; }
    // Cleanup must not throw back into combat, including during a failed conversion.
    if (changed) try { ((void (*)(void *))(image + VeritasSetActiveTexture))(previous); } catch (...) {}
    if (temporary) try { ((void (*)(void *))(image + VeritasReleaseTexture))(temporary); } catch (...) {}
    if (readable) try { ((void (*)(void *))(image + VeritasDestroyObject))(readable); } catch (...) {}
    return png;
}
static NSString *ObjectTypeName(uintptr_t image, void *object) {
    if (!object) return nil;
    void *type = ((void *(*)(void *))(image + VeritasGetObjectType))(object);
    return type ? ManagedString(((void *(*)(void *))(image + VeritasGetTypeName))(type)) : nil;
}
static void *NamedField(uintptr_t image, void *object, NSString *name, bool *found) {
    *found = false;
    if (!object) return nullptr;
    void *type = ((void *(*)(void *))(image + VeritasGetObjectType))(object);
    void *fields = type ? ((void *(*)(void *, int, void *))(image + VeritasGetFields))(type, 60, nullptr) : nullptr;
    uint32_t count = CountAt(fields, VeritasArrayLength);
    if (!fields || count > 512) return nullptr;
    void *match = nullptr;
    for (unsigned index = 0; index < count; index++) {
        void *field = PointerAt(fields, VeritasArrayItems + index * sizeof(void *));
        if (!field || ![ObjectTypeName(image, field) isEqualToString:@"MonoField"]) continue;
        void *fieldName = ((void *(*)(void *))(image + VeritasFieldName))(field);
        if (![ManagedString(fieldName) isEqualToString:name]) continue;
        if (match) return nullptr;
        match = field;
    }
    if (!match) return nullptr;
    *found = true;
    return ((void *(*)(void *, void *, void *))(image + VeritasFieldValue))(match, object, nullptr);
}
NSArray<NSNumber *> *VeritasExtraLineup(uintptr_t image, void *lineup) {
    try {
        bool found; void *team = NamedField(image, lineup, @"ExtraTeam", &found);
        if (!found) return nil;
        if (!team) return @[];
        if (![ObjectTypeName(image, team) isEqualToString:@"LineUpCharacter[]"]) return nil;
        unsigned count = CountAt(team, VeritasArrayLength);
        if (count > 32) return nil;
        NSMutableArray *ids = [NSMutableArray array];
        for (unsigned index = 0; index < count; index++) {
            void *character = PointerAt(team, VeritasArrayItems + index * sizeof(void *));
            uint32_t uid = CountAt(character, VeritasLineupCharacterID);
            if (uid) [ids addObject:@(uid)];
        }
        return ids;
    } catch (...) { return nil; }
}
int VeritasFormationTeam(uintptr_t image, void *component) {
    try {
        bool found; void *boxed = NamedField(image, component, @"_Team", &found);
        if (!found || ![ObjectTypeName(image, boxed) isEqualToString:@"TeamType"]) return -1;
        return (int32_t)CountAt(boxed, VeritasBoxedValue);
    } catch (...) { return -1; }
}
uint32_t VeritasReadSkillID(uintptr_t image, void *skill) {
    try {
        bool found; void *boxed = NamedField(image, skill, @"SkillConfigID", &found);
        if (!found || ![ObjectTypeName(image, boxed) isEqualToString:@"UInt32"]) return 0;
        return CountAt(boxed, VeritasBoxedValue);
    } catch (...) { return 0; }
}
NSData *VeritasCapturePropertyIcon(uintptr_t image, NSString *property) {
    try {
        NSDictionary *names = VeritasReadEnumNames(image, VeritasTypeAvatarPropertyType);
        NSNumber *key = [[names allKeysForObject:property] firstObject];
        if (!key) return nil;
        void *row = ((void *(*)(int))(image + VeritasPropertyIconRow))(key.intValue);
        bool found; void *path = NamedField(image, row, @"IconPath", &found);
        return found && [ObjectTypeName(image, path) isEqualToString:@"String"] ? VeritasCaptureSprite(image, path) : nil;
    } catch (...) { return nil; }
}
NSData *VeritasCaptureAvatar(uintptr_t image, uint32_t avatar) {
    try { return VeritasCaptureSprite(image, ((void *(*)(uint32_t))(image + VeritasAvatarIconPath))(avatar)); }
    catch (...) { return nil; }
}
NSData *VeritasCaptureEnemy(uintptr_t image, void *row) {
    try { return VeritasCaptureSprite(image, ((void *(*)(void *))(image + VeritasMonsterIconPath))(row)); }
    catch (...) { return nil; }
}
static NSCache *PortraitCache(void) {
    static NSCache *cache; static dispatch_once_t once;
    dispatch_once(&once, ^{ cache = [NSCache new]; cache.countLimit = 64; cache.totalCostLimit = 32 * 1024 * 1024; });
    return cache;
}
void VeritasCachePortrait(NSString *key, NSData *png) {
    UIImage *image = png ? [UIImage imageWithData:png] : nil;
    if (image) [PortraitCache() setObject:image forKey:key cost:(NSUInteger)(image.size.width * image.size.height * 4)];
}
UIImage *VeritasCachedPortrait(NSString *key) { return [PortraitCache() objectForKey:key]; }
