#import <UIKit/UIKit.h>
#import "Assets.h"
#include <cassert>
#include <cstring>
#include <stdexcept>
static char klass[128], texture[32], readable[32], names[64], values[64], nameHP[64], nameMax[64], png[64];
static char fields[64], fieldExtra[64], fieldSkill[64], extraName[64], skillName[64], extra[64], boxed[32];
static char fieldTeam[64], teamName[64], boxedTeam[32], teamTypeName[64];
static char arrayTypeName[64], uintTypeName[64], fieldTypeName[64], character[128];
static char renderNames[64], renderValues[64], defaultName[64], linearName[64];
static int lastTypeIndex;
static void *active;
static unsigned sets, releases, destroys, failure;
void *FakeClass(int index) { lastTypeIndex = index; return klass; }
void *FakeType(void *type) { assert(type == klass + 0x68); return klass; }
void *FakeEnumNames(void *, void *) {
    if (lastTypeIndex == 44 || lastTypeIndex == 45) {
        void *string = lastTypeIndex == 44 ? defaultName : linearName;
        memcpy(renderNames + 32, &string, 8); return renderNames;
    }
    return names;
}
void *FakeEnumValues(void *, void *) {
    if (lastTypeIndex == 44 || lastTypeIndex == 45) {
        int32_t value = lastTypeIndex == 44 ? 7 : 1; memcpy(renderValues + 32, &value, 4); return renderValues;
    }
    return values;
}
void *FakeLoad(void *, void *, bool, void *) { return texture; }
void *FakeTexture(void *, void *) { return texture; }
int FakeWidth(void *) { return failure == 4 ? 4096 : 64; }
void *FakeTemporary(int width, int height, int depth, int format, int readWrite) { assert(width == 64 && height == 64 && depth == 0 && format == 7 && readWrite == 1); return names; }
void FakeBlit(void *, void *) { active = names; if (failure == 1) throw std::runtime_error("blit"); }
void *FakeActive(void) { return active; }
void FakeSetActive(void *value) { active = value; sets++; }
void *FakeAllocate(void *type) { assert(type == klass); return readable; }
void FakeConstructor(void *object, int w, int h) { assert(object == readable && w == 64 && h == 64); }
void FakeRead(void *, FakeRect rect, int x, int y) {
    assert(rect.x == 0 && rect.y == 0 && rect.width == 64 && rect.height == 64 && x == 0 && y == 0);
    if (failure == 2) throw std::runtime_error("read");
}
void FakeApply(void *) { if (failure == 3) throw std::runtime_error("apply"); }
void *FakeEncode(void *) {
    if (failure == 7) @throw [NSException exceptionWithName:@"test" reason:@"encode" userInfo:nil];
    return png;
}
void FakeRelease(void *) { releases++; if (failure == 5) throw std::runtime_error("release"); }
void FakeDestroy(void *) { destroys++; if (failure == 6) throw std::runtime_error("destroy"); }
void *FakeAvatarPath(uint32_t) { return nameHP; }
void *FakeEnemyPath(void *) { return nameHP; }
void *FakeObjectType(void *object) { return object; }
void *FakeTypeName(void *object) { return object == boxedTeam ? teamTypeName : object == extra ? arrayTypeName : (object == fieldExtra || object == fieldSkill || object == fieldTeam) ? fieldTypeName : uintTypeName; }
void *FakeFields(void *, int flags, void *) { assert(flags == 60); return fields; }
void *FakeFieldName(void *field) { return field == fieldTeam ? teamName : field == fieldExtra ? extraName : skillName; }
void *FakeFieldValue(void *field, void *, void *) { return field == fieldTeam ? boxedTeam : field == fieldExtra ? extra : boxed; }
void *FakePropertyRow(int) { return klass; }
static void PutCount(char *data, uint32_t value) { memcpy(data + 24, &value, 4); }
static void PutString(char *data, NSString *string) {
    uint32_t length = (uint32_t)string.length; memcpy(data + 16, &length, 4);
    [string getCharacters:(unichar *)(data + 20) range:NSMakeRange(0, length)];
}
int main(void) { @autoreleasepool {
    PutCount(fields, 3); void *fieldObjects[] = {fieldExtra, fieldSkill, fieldTeam}; memcpy(fields + 32, fieldObjects, sizeof(fieldObjects));
    PutString(teamName, @"_Team"); PutString(teamTypeName, @"TeamType"); uint32_t team = 2; memcpy(boxedTeam + 16, &team, 4);
    PutString(extraName, @"ExtraTeam"); PutString(skillName, @"SkillConfigID");
    PutString(arrayTypeName, @"LineUpCharacter[]"); PutString(uintTypeName, @"UInt32"); PutString(fieldTypeName, @"MonoField");
    assert(VeritasFormationTeam(0, klass) == 2);
    PutCount(extra, 1); void *oneCharacter = character; memcpy(extra + 32, &oneCharacter, sizeof(oneCharacter));
    uint32_t avatar = 1002, skill = 123456; memcpy(character + 108, &avatar, 4); memcpy(boxed + 16, &skill, 4);
    assert(([VeritasExtraLineup(0, klass) isEqual:@[@1002]]));
    assert(VeritasReadSkillID(0, klass) == 123456);
    PutCount(extra, 33); assert(!VeritasExtraLineup(0, klass)); PutCount(extra, 1);
    PutString(skillName, @"ExtraTeam"); assert(!VeritasExtraLineup(0, klass)); PutString(skillName, @"SkillConfigID");
    PutCount(fields, 0); assert(!VeritasExtraLineup(0, klass) && VeritasReadSkillID(0, klass) == 0); PutCount(fields, 3);
    PutCount(renderNames, 1); PutCount(renderValues, 1); PutString(defaultName, @"Default"); PutString(linearName, @"Linear");
    void *type = klass; memcpy(texture, &type, 8);
    PutCount(names, 2); PutCount(values, 2); PutString(nameHP, @"CurrentHP"); PutString(nameMax, @"MaxHP");
    void *strings[] = {nameHP, nameMax}; memcpy(names + 32, strings, sizeof(strings));
    int32_t numbers[] = {10, 1}; memcpy(values + 32, numbers, sizeof(numbers));
    NSDictionary *labels = VeritasReadEnumNames(0, 0);
    assert([labels[@10] isEqual:@"CurrentHP"] && [labels[@1] isEqual:@"MaxHP"]);
    PutCount(values, 1); assert(!VeritasReadEnumNames(0, 0)); PutCount(values, 2);
    PutCount(png, 3); memcpy(png + 32, "PNG", 3);
    for (failure = 0; failure <= 7; failure++) {
        sets = releases = destroys = 0; active = klass;
        NSData *result = VeritasCaptureAvatar(0, 1001);
        assert(active == klass);
        if (failure == 4) { assert(!result && !sets && !releases && !destroys); continue; }
        assert(releases == 1);
        if (failure == 1) { assert(!result && sets == 1 && !destroys); continue; }
        assert(sets == 2 && destroys == 1);
        assert((result != nil) == (failure == 0 || failure == 5 || failure == 6));
        if (result) assert(result.length == 3 && !memcmp(result.bytes, "PNG", 3));
    }
    assert(!VeritasCaptureSprite(0, nullptr));
} }
