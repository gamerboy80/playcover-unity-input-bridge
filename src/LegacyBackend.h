// unity-legacy-v1 backend. Included by the common host after its state declarations.
#ifndef GameLegacyButtons
#define GameLegacyButtons 1
#endif
#ifndef GameLegacyAxisXName
#define GameLegacyAxisXName "Mouse X"
#define GameLegacyAxisYName "Mouse Y"
#define GameLegacyAxisScrollName "Mouse ScrollWheel"
#endif
static uint8_t legacyKeys[14];
static uint8_t heldKeys[512], pendingKeyDown[512], pendingKeyUp[512], frameKeyDown[512], frameKeyUp[512];
static BOOL (*legacyKeyOriginal[3])(int);
static BOOL (*legacyAnyOriginal[2])(void);
static unsigned legacyKeyWrites, legacyKeyReads, legacyMouseReads, legacyScrollReads, legacyAxisReads;
static unsigned legacyPositiveKeys, legacyPositiveScrolls, legacyNamedAxes, legacyNonzeroAxes;
static uint16_t legacyButtons, pendingDown, pendingUp, frameDown, frameUp;
static float pendingX,pendingY,pendingScrollX,pendingScrollY,frameX,frameY,frameScrollX,frameScrollY;
static int legacyFrame=-1;
static BOOL (*legacyButtonOriginal[3])(int);
static float (*legacyAxisOriginal[2])(void *);
static void (*legacyPositionOriginal)(float *);
static BOOL legacyHasPosition;

static unsigned legacyKey(unsigned key) {
    if (key>=15 && key<=40) return 'a'+key-15;
    if (key>=41 && key<=49) return '1'+key-41;
    if (key>=94 && key<=105) return 282+key-94;
    static const unsigned short special[94]={
        [1]=32,[2]=13,[3]=9,[4]=96,[5]=39,[6]=59,[7]=44,[8]=46,[9]=47,[10]=92,
        [11]=91,[12]=93,[13]=45,[14]=61,[50]=48,[51]=304,[52]=303,[53]=308,[54]=307,
        [55]=306,[56]=305,[57]=310,[58]=309,[60]=27,[61]=276,[62]=275,[63]=273,
        [64]=274,[65]=8,[66]=281,[67]=280,[68]=278,[69]=279,[70]=277,[71]=127,
        [72]=301,[73]=300,[77]=271,[78]=267,[79]=268,[80]=270,[81]=269,[82]=266,
        [83]=272,[84]=256,[85]=257,[86]=258,[87]=259,[88]=260,[89]=261,[90]=262,
        [91]=263,[92]=264,[93]=265};
    return key<94 ? special[key] : 0;
}

static void legacyPoll(void) {
    int frame=((int (*)(void))(slide+GameFrameCount))();
    if (legacyFrame==frame) return;
    legacyFrame=frame;
    memcpy(frameKeyDown,pendingKeyDown,sizeof(frameKeyDown));
    memcpy(frameKeyUp,pendingKeyUp,sizeof(frameKeyUp));
    memset(pendingKeyDown,0,sizeof(pendingKeyDown));
    memset(pendingKeyUp,0,sizeof(pendingKeyUp));
    frameDown=pendingDown; frameUp=pendingUp; pendingDown=pendingUp=0;
    frameX=pendingX; frameY=pendingY; frameScrollX=pendingScrollX; frameScrollY=pendingScrollY;
    pendingX=pendingY=pendingScrollX=pendingScrollY=0;
}
static BOOL legacyButton(int button, unsigned kind) {
    legacyMouseReads++;
    legacyPoll();
    BOOL value=NO;
    if (GameLegacyButtons && button>=0 && button<5) {
        uint16_t bits=kind==0 ? legacyButtons : kind==1 ? frameDown : frameUp;
        value=(bits & (1u<<button))!=0;
    }
    return value || (legacyButtonOriginal[kind] && legacyButtonOriginal[kind](button));
}
static BOOL legacyHeld(int b) { return legacyButton(b,0); }
static BOOL legacyDown(int b) { return legacyButton(b,1); }
static BOOL legacyUp(int b) { return legacyButton(b,2); }
static void legacyPosition(float *result) {
    legacyMouseReads++;
    if (!legacyHasPosition && legacyPositionOriginal) { legacyPositionOriginal(result); return; }
    result[0]=mouseState.x; result[1]=mouseState.y; result[2]=0;
}
static void legacyScrollForCaller(float *result, uintptr_t caller) {
    legacyScrollReads++;
    legacyPoll();
    // UI expects notches; InControl gameplay expects its profile's wheel units.
    float divisor=caller==slide+GameUIScrollReturn ? GameLegacyScrollUnitsPerStep : 1;
    result[0]=frameScrollX/divisor; result[1]=frameScrollY/divisor;
    if (frameScrollX!=0 || frameScrollY!=0) legacyPositiveScrolls++;
}
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wframe-address"
__attribute__((noinline)) static void legacyScroll(float *result) {
    uintptr_t caller=(uintptr_t)__builtin_return_address(0);
    // This exact wrapper saves x29/x30; its parent identifies UI versus gameplay.
    if (caller==slide+GameScrollWrapperReturn)
        caller=(uintptr_t)__builtin_return_address(1);
    static BOOL reportedUI;
    if (!reportedUI && caller==slide+GameUIScrollReturn) {
        reportedUI=YES;
        if (output) { fprintf(output,"UI scroll caller verified; normalizing wheel units to notches\n"); fflush(output); }
    }
    legacyScrollForCaller(result,caller);
}
#pragma clang diagnostic pop
static BOOL legacyName(void *string, const char *name) {
    if (!string) return NO;
    int length=*(int *)((uint8_t *)string+16);
    if (length<0 || (size_t)length!=strlen(name)) return NO;
    const uint16_t *chars=(const void *)((uint8_t *)string+20);
    // HSR requests lowercase axis labels; accept the same fixed names in either case.
    for (int i=0;i<length;i++) {
        unsigned a=chars[i], b=(unsigned char)name[i];
        if (a>='A' && a<='Z') a+='a'-'A';
        if (b>='A' && b<='Z') b+='a'-'A';
        if (a!=b) return NO;
    }
    return YES;
}
static float legacyAxis(void *name, unsigned raw, uintptr_t caller) {
    legacyAxisReads++;
    legacyPoll();
    // Bounded configuration diagnostics; axis labels are not typed input.
    static char seen[8][65];
    static unsigned count;
    if (output && name && count<8) {
        int length=*(int *)((uint8_t *)name+16);
        if (length>0 && length<=64) {
            char label[65]={0};
            const uint16_t *chars=(void *)((uint8_t *)name+20);
            for (int i=0;i<length;i++) label[i]=chars[i]<128 ? (char)chars[i] : '?';
            BOOL known=NO;
            for (unsigned i=0;i<count;i++) if (!strcmp(seen[i],label)) known=YES;
            if (!known) {
                memcpy(seen[count++],label,(size_t)length+1);
                fprintf(output,"Legacy axis label=%s caller=%llx\n",label,(unsigned long long)(caller-slide)); fflush(output);
            }
        }
    }
    if (legacyName(name,"Mouse X") || legacyName(name,GameLegacyAxisXName)) {
        legacyNamedAxes++; legacyNonzeroAxes+=frameX!=0; return frameX*.05f;
    }
    if (legacyName(name,"Mouse Y") || legacyName(name,GameLegacyAxisYName)) {
        legacyNamedAxes++; legacyNonzeroAxes+=frameY!=0; return frameY*.05f;
    }
    if (legacyName(name,"Mouse ScrollWheel") || legacyName(name,GameLegacyAxisScrollName))
        return frameScrollY;
    return legacyAxisOriginal[raw] ? legacyAxisOriginal[raw](name) : 0;
}
static float legacyAxisSmooth(void *s) { return legacyAxis(s,0,(uintptr_t)__builtin_return_address(0)); }
static float legacyAxisRaw(void *s) { return legacyAxis(s,1,(uintptr_t)__builtin_return_address(0)); }

static BOOL legacyReadKey(int code, unsigned kind) {
    legacyKeyReads++;
    legacyPoll();
    const uint8_t *state=kind==0 ? heldKeys : kind==1 ? frameKeyDown : frameKeyUp;
    BOOL value=code>=0 && code<512 && state[code];
    if (value) legacyPositiveKeys++;
    return value ||
        (legacyKeyOriginal[kind] && legacyKeyOriginal[kind](code));
}
static BOOL legacyKeyHeld(int code) { return legacyReadKey(code,0); }
static BOOL legacyKeyDown(int code) { return legacyReadKey(code,1); }
static BOOL legacyKeyUp(int code) { return legacyReadKey(code,2); }
static BOOL legacyAny(unsigned kind) {
    legacyPoll();
    const uint8_t *state=kind ? frameKeyDown : heldKeys;
    for (unsigned i=0;i<512;i++) if (state[i]) return YES;
    return legacyAnyOriginal[kind] && legacyAnyOriginal[kind]();
}
static BOOL legacyAnyHeld(void) { return legacyAny(0); }
static BOOL legacyAnyDown(void) { return legacyAny(1); }

static BOOL initializeLegacy(void) {
    const uintptr_t offsets[]={GameMousePositionSlot,GameMouseScrollSlot,GameMouseButtonSlot,
        GameMouseButtonDownSlot,GameMouseButtonUpSlot,GameAxisSlot,GameAxisRawSlot,
        GameKeySlot,GameKeyDownSlot,GameKeyUpSlot,GameAnyKeySlot,GameAnyKeyDownSlot};
    void *replacements[]={(void *)legacyPosition,(void *)legacyScroll,(void *)legacyHeld,
        (void *)legacyDown,(void *)legacyUp,(void *)legacyAxisSmooth,(void *)legacyAxisRaw,
        (void *)legacyKeyHeld,(void *)legacyKeyDown,(void *)legacyKeyUp,(void *)legacyAnyHeld,(void *)legacyAnyDown};
#ifdef GameResolveICall
    if (GameResolveICall) {
        // A populated wrapper proves Unity registered its internal calls.
        BOOL registered=NO;
        for (unsigned i=0;i<12;i++) if (*(void **)(slide+offsets[i])) registered=YES;
        if (!registered) return NO;
    }
    // Some players never initialize unused legacy getters; resolve their verified callbacks explicitly.
    const char *names[]={
        "UnityEngine.Input::get_mousePosition_Injected(UnityEngine.Vector3&)",
        "UnityEngine.Input::get_mouseScrollDelta_Injected(UnityEngine.Vector2&)",
        "UnityEngine.Input::GetMouseButton(System.Int32)",
        "UnityEngine.Input::GetMouseButtonDown(System.Int32)",
        "UnityEngine.Input::GetMouseButtonUp(System.Int32)",
        "UnityEngine.Input::GetAxis(System.String)","UnityEngine.Input::GetAxisRaw(System.String)",
        "UnityEngine.Input::GetKeyInt(UnityEngine.KeyCode)",
        "UnityEngine.Input::GetKeyDownInt(UnityEngine.KeyCode)","UnityEngine.Input::GetKeyUpInt(UnityEngine.KeyCode)",
        "UnityEngine.Input::get_anyKey()","UnityEngine.Input::get_anyKeyDown()"};
    if (GameResolveICall) for (unsigned i=0;i<12;i++) {
        void **slot=(void **)(slide+offsets[i]);
        if (!*slot) *slot=((void *(*)(const char *))(slide+GameResolveICall))(names[i]);
    }
#endif
    for (unsigned i=0;i<12;i++) if (!*(void **)(slide+offsets[i])) return NO;
    legacyPositionOriginal=*(void **)(slide+GameMousePositionSlot);
    for (unsigned i=0;i<3;i++) legacyButtonOriginal[i]=*(void **)(slide+offsets[i+2]);
    for (unsigned i=0;i<2;i++) legacyAxisOriginal[i]=*(void **)(slide+offsets[i+5]);
    for (unsigned i=0;i<3;i++) legacyKeyOriginal[i]=*(void **)(slide+offsets[i+7]);
    for (unsigned i=0;i<2;i++) legacyAnyOriginal[i]=*(void **)(slide+offsets[i+10]);
    for (unsigned i=0;i<12;i++) *(void **)(slide+offsets[i])=replacements[i];
    return YES;
}
static void legacySendKeyboard(void) {
    for (unsigned k=1;k<110;k++) {
        unsigned mask=1u<<(k%8), value=keys[k/8]&mask;
        if (value==(legacyKeys[k/8]&mask)) continue;
        unsigned code=legacyKey(k);
        if (code && code<512) {
            legacyKeyWrites++;
            heldKeys[code]=value!=0;
            if (value) pendingKeyDown[code]=1; else pendingKeyUp[code]=1;
        }
    }
    memcpy(legacyKeys,keys,sizeof(keys));
}
static void legacySendMouse(void) {
    uint16_t changed=legacyButtons^mouseState.buttons;
    pendingDown|=changed&mouseState.buttons;
    pendingUp|=changed&legacyButtons;
    legacyButtons=mouseState.buttons;
    pendingX+=mouseState.dx; pendingY+=mouseState.dy;
    pendingScrollX+=mouseState.sx/WheelUnitsPerStep*GameLegacyScrollUnitsPerStep;
    pendingScrollY+=mouseState.sy/WheelUnitsPerStep*GameLegacyScrollUnitsPerStep;
    legacyHasPosition=YES;
    mouseState.dx=mouseState.dy=mouseState.sx=mouseState.sy=0;
}
