#import <Foundation/Foundation.h>
@class UIImage;
#ifdef __cplusplus
extern "C" {
#endif
NSArray<NSNumber *> *VeritasExtraLineup(uintptr_t image, void *lineup);
int VeritasFormationTeam(uintptr_t image, void *component);
uint32_t VeritasReadSkillID(uintptr_t image, void *skill);
NSData *VeritasCapturePropertyIcon(uintptr_t image, NSString *property);
NSDictionary<NSNumber *, NSString *> *VeritasReadEnumNames(uintptr_t image, unsigned typeIndex);
NSData *VeritasCaptureAvatar(uintptr_t image, uint32_t avatar);
NSData *VeritasCaptureEnemy(uintptr_t image, void *row);
NSData *VeritasCaptureSprite(uintptr_t image, void *path);
void VeritasCachePortrait(NSString *key, NSData *png);
UIImage *VeritasCachedPortrait(NSString *key);
#ifdef __cplusplus
}
#endif
