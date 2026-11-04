// Unity may store statics in one shared region or separate IL2CPP class storage.
static uintptr_t inputStatic(uintptr_t reference, uintptr_t field) {
    uintptr_t storage=*(uintptr_t *)(slide+reference);
#if GameTypeStatics
    // IL2CPP metadata references carry an odd token until the class is resolved.
    if (storage & 1) return 0;
    if (storage) storage=*(uintptr_t *)(storage+GameFieldStaticFields);
#endif
    return storage ? *(uintptr_t *)(storage+field) : 0;
}
