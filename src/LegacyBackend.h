// unity-legacy-v1 backend. Included by the common host after its state declarations.
static uint8_t legacyKeys[14];
static uint8_t heldKeys[512], pendingKeyDown[512], pendingKeyUp[512], frameKeyDown[512], frameKeyUp[512];
static BOOL (*legacyKeyOriginal[3])(int);
static BOOL (*legacyAnyOriginal[2])(void);
static unsigned legacyKeyWrites, legacyKeyReads, legacyMouseReads, legacyScrollReads, legacyAxisReads;
static unsigned legacyPositiveKeys, legacyPositiveScrolls, legacyNamedAxes;
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
    if (button>=0 && button<5) {
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
static void legacyScroll(float *result) { legacyScrollReads++; legacyPoll(); result[0]=frameScrollX; result[1]=frameScrollY;
    if (frameScrollX!=0 || frameScrollY!=0) legacyPositiveScrolls++; }
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
static float legacyAxis(void *name, unsigned raw) {
    legacyAxisReads++;
    legacyPoll();
    if (legacyName(name,"Mouse X")) { legacyNamedAxes++; return frameX*.05f; }
    if (legacyName(name,"Mouse Y")) { legacyNamedAxes++; return frameY*.05f; }
    if (legacyName(name,"Mouse ScrollWheel")) return frameScrollY;
    return legacyAxisOriginal[raw] ? legacyAxisOriginal[raw](name) : 0;
}
static float legacyAxisSmooth(void *s) { return legacyAxis(s,0); }
static float legacyAxisRaw(void *s) { return legacyAxis(s,1); }

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
    for (unsigned i=0;i<12;i++) if (!*(void **)(slide+offsets[i])) return NO;
    legacyPositionOriginal=*(void **)(slide+GameMousePositionSlot);
    for (unsigned i=0;i<3;i++) legacyButtonOriginal[i]=*(void **)(slide+offsets[i+2]);
    for (unsigned i=0;i<2;i++) legacyAxisOriginal[i]=*(void **)(slide+offsets[i+5]);
    for (unsigned i=0;i<3;i++) legacyKeyOriginal[i]=*(void **)(slide+offsets[i+7]);
    for (unsigned i=0;i<2;i++) legacyAnyOriginal[i]=*(void **)(slide+offsets[i+10]);
    for (unsigned i=0;i<12;i++) *(void **)(slide+offsets[i])=replacements[i];
    return YES;
}
static void sendKeyboard(void) {
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
static void sendMouse(void) {
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
