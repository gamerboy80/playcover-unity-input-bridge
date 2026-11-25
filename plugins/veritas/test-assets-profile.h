#pragma once
#import <Foundation/Foundation.h>
#include <stdint.h>
#define VERITAS_PROFILE_H
extern "C" {
void *FakeClass(int);
void *FakeType(void *);
void *FakeEnumNames(void *, void *);
void *FakeEnumValues(void *, void *);
void *FakeLoad(void *, void *, bool, void *);
void *FakeTexture(void *, void *);
int FakeWidth(void *);
void *FakeTemporary(int, int, int, int, int);
void FakeBlit(void *, void *);
void *FakeActive(void);
void FakeSetActive(void *);
void *FakeAllocate(void *);
void FakeConstructor(void *, int, int);
struct FakeRect { float x, y, width, height; };
void FakeRead(void *, FakeRect, int, int);
void FakeApply(void *);
void *FakeEncode(void *);
void FakeRelease(void *);
void FakeDestroy(void *);
void *FakeAvatarPath(uint32_t);
void *FakeEnemyPath(void *);
}
#define VeritasResolveClass (uintptr_t)FakeClass
#define VeritasTypeObject (uintptr_t)FakeType
#define VeritasClassType 0x68
#define VeritasTypeSprite 42
#define VeritasEnumNames (uintptr_t)FakeEnumNames
#define VeritasEnumValues (uintptr_t)FakeEnumValues
#define VeritasLoadSprite (uintptr_t)FakeLoad
#define VeritasSpriteTexture (uintptr_t)FakeTexture
#define VeritasTextureWidth (uintptr_t)FakeWidth
#define VeritasTextureHeight (uintptr_t)FakeWidth
#define VeritasTemporaryTexture (uintptr_t)FakeTemporary
#define VeritasBlitTexture (uintptr_t)FakeBlit
#define VeritasActiveTexture (uintptr_t)FakeActive
#define VeritasSetActiveTexture (uintptr_t)FakeSetActive
#define VeritasAllocateObject (uintptr_t)FakeAllocate
#define VeritasTextureConstructor (uintptr_t)FakeConstructor
#define VeritasReadPixels (uintptr_t)FakeRead
#define VeritasApplyTexture (uintptr_t)FakeApply
#define VeritasEncodePNG (uintptr_t)FakeEncode
#define VeritasReleaseTexture (uintptr_t)FakeRelease
#define VeritasDestroyObject (uintptr_t)FakeDestroy
#define VeritasAvatarIconPath (uintptr_t)FakeAvatarPath
#define VeritasMonsterIconPath (uintptr_t)FakeEnemyPath
#define VeritasArrayLength 24
#define VeritasArrayItems 32
extern "C" {
void *FakeObjectType(void *);
void *FakeTypeName(void *);
void *FakeFields(void *, int, void *);
void *FakeFieldName(void *);
void *FakeFieldValue(void *, void *, void *);
void *FakePropertyRow(int);
}
#define VeritasStringLength 16
#define VeritasStringCharacters 20
#define VeritasObjectClass 0
#define VeritasBoxedValue 16
#define VeritasLineupCharacterID 108
#define VeritasTypeAvatarPropertyType 43
#define VeritasGetObjectType (uintptr_t)FakeObjectType
#define VeritasGetTypeName (uintptr_t)FakeTypeName
#define VeritasGetFields (uintptr_t)FakeFields
#define VeritasFieldName (uintptr_t)FakeFieldName
#define VeritasFieldValue (uintptr_t)FakeFieldValue
#define VeritasPropertyIconRow (uintptr_t)FakePropertyRow

#define VeritasTypeRenderTextureFormat 44
#define VeritasTypeRenderTextureReadWrite 45

#define VeritasTypeTexture2D 46
