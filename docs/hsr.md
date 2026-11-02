# HSR 4.6.0

Profile: `com.HoYoverse.hkrpgoversea-4.6.0` (alias `hsr`); bundle: `com.HoYoverse.hkrpgoversea`; executable: `hkrpg`.
The initial physical gameplay test failed: keyboard, mouse capture and scrolling
did not respond; some buttons also failed. The user then confirmed keyboard
movement works after hooking GetKey callbacks directly. Native capture and
mouse look were subsequently confirmed after scoped cursor checks and matching
HSR’s lowercase axis labels. Camera zoom was then confirmed with 120-unit scroll steps, followed by correct
menu cursor visibility after force-show/host hide balancing fixes. Menu scrolling, menu cursor visibility and camera zoom are now user-confirmed,
including reasonable menu speed after wrapper-aware normalization. Broader
button coverage remains unverified. This profile
is experimental.

```sh
python3 patch.py install --profile hsr
python3 patch.py status --profile hsr
python3 patch.py update --profile hsr
python3 patch.py restore --profile hsr
```

Builds and backups are separate from ZZZ under the canonical profile ID.
Existing `.local/hsr/` backups are reused without moving them. `--app` can auto-select this exact build.
Disable PlayCover keymapping and preserve the PlayTools pointer-lock fix.

## Analysis

Original framework SHA-256:
`29c5e8960e90bdd1f877f2b3e040deb965506325c922e826c80fee5840115dcd`.
Examined global metadata SHA-256:
`6ea5b6f3e444fd530c2d76ae89cae81d75a3eb80bcb4ab69cfee8ced2570e3cf`.
Startup metadata SHA-256:
`bc2ddd0ce7e9db6790a48e5d5e201094f31aef5c9d0070fae862e9431994b298`.

This metadata has an MHY header, body at `+0x208`, 70-byte type rows and 26-byte
method rows. Loader `0xea31894` and string decoder `0xea32848` were traced to
recover names and associate methods with native table `0x14b2c9f0`. 139 image
names were recovered, including InControl; ZZZ's Unity Input System assembly
was absent. InControl's Unity keyboard/mouse providers use legacy input here.

Two predicates return true: `AppUtils.IsPCLayout` at `0xf2bde8` and
`UIUtils.IsPCMode` at `0x226c378`. The profile records exact original bytes and
the replacement `mov w0,#1; ret`. These text VM addresses equal file offsets.
OS/network identity predicates are not changed. Other builds require new analysis.

## Backend

`unity-legacy-v1` shares AppKit monitoring, capture/focus fixes, key mapping and
trackpad conversion with ZZZ. `src/LegacyBackend.h` supplies game-facing input.
The first attempt called `Input.SetKey(KeyCode,bool)` at `0xe89c394`, but
physical keyboard input failed. The revised backend hooks GetKey/GetKeyDown/
GetKeyUp and anyKey/anyKeyDown callbacks directly. Shared Unity Key indices map
to legacy UnityEngine.KeyCode values; held state persists and pending edges are
published once per Unity frame, with original callbacks preserved as fallback.
Disassembly of InControl.UnityKeyboardProvider.GetKeyIsPressed confirms it
reads the GetKey callback via `0xe89c364`. Runtime counters confirm repeated
keyboard, mouse, scroll and axis reads with all 12 hooks intact. This proves
the callback path is active, not that physical gameplay input works.

Three additional instruction edits bypass only the mobile checks within
MouseInputController.ShowCursor (`0x1b04180`), HideCursor (`0x1b04248`), and
UseCursorMode (`0x1b04520`). The original methods otherwise retain their normal
PC cursor state and gamepad/forced-cursor logic. Global platform identity stays
unchanged. The user confirmed capture with these edits installed. Camera motion required
case-insensitive matching of the actual `mouse x` and `mouse y` axis labels; the
user then confirmed mouse look works.

Mouse getters tail-call writable callback slots relative to VM `0x15a4f270`:

| Offset | Native signature / purpose |
| --- | --- |
| `+0xd40`, `+0xd68`, `+0xd50` | `BOOL(int)`; key held/down/up |
| `+0xdd8`, `+0xde0` | `BOOL(void)`; any key held/down |
| `+0xd78`, `+0xd80` | `float(IL2CppString *)`; GetAxis/GetAxisRaw |
| `+0xda0`, `+0xda8`, `+0xdb0` | `BOOL(int)`; mouse held/down/up |
| `+0xeb8` | `void(float[3])`; mouse position |
| `+0xec0` | `void(float[2])`; scroll |
| `+0xe20` | `BOOL(void)`; mouse present |

Apply the dyld slide to VM addresses. `Time.frameCount` at `0xe8732f4` defines
frame boundaries. Pending edges/deltas are published on the next frame's first
poll and remain stable across repeated reads. Unknown axes and native buttons
preserve original callbacks; position preserves the original until host input
arrives. Mouse X/Y currently use a provisional 0.05 scale, requiring calibration.

Tests exercise key translation/releases, per-frame button/scroll state, callback
installation and native fallback. Both backends build with warnings as errors.
Initialization and synthetic tests do not establish physical gameplay success.

The legacy backend logs at most 60 aggregate diagnostic lines, one per five
seconds: event/state writes, getter reads, nonzero returns and hook integrity.
No key identities, text or pointer coordinates are logged.

HSR's MouseBindingSource static constructor (`0xc1d1bf0`) initializes four scales
at static storage `0x15a58cc0 + 0x56b0` to 0.05. Its scroll binding reads the
provider's scroll value and applies that scale (`0xc1d1548` onward). Returning
one unit per notch reduced a step to 0.05; the revised profile explicitly supplies
120 units per notch through `bridge.scroll_units_per_step`. Runtime counters
already confirmed nonzero legacy scroll reads, so this change targets the
binding's magnitude rather than host event delivery. The user confirmed camera zoom works with this scale. Menu scrolling works after the UI redirect below, but initially ran too fast.

Menu cursor paths also contain mobile early returns in ForceShowCursor
(`0x1b03e8c`) and ForceShowCursorBySDKUI (`0x1b03fb4`). Their scoped profile edits
allow the original menu cursor state and unlock calls to run. The host balances
its own AppKit hide claims before a visibility refresh and on release, preventing
repeated captured-cursor refreshes from leaving the pointer hidden in menus.

InControlInputModule.Process (`0xc1c32c0`) dispatches navigation/custom processors
and ends with only ProcessTouchEvents, guarded by its touch-enable byte at +0x6f.
No call to its existing ProcessMouseEvent appears in that method. The UI profile
redirects the BL at `0xc1c33a0` to ProcessMouseEvent (`0xc1c4e98`) and removes the
touch-only guard branch at `0xc1c3398`. Navigation and active-module selection are
preserved. ProcessMouseEvent uses PointerInputModule.GetMousePointerEventData,
which reads position and scroll through BaseInput's virtual getters and raycasts
the UI. Locked cursors retain Unity's offscreen pointer behavior. This is scoped
to menu input; global mobile platform identity remains unchanged.

The user confirmed menu scrolling after the redirect. PointerInputModule expects
notches, while gameplay uses 120 wheel units. `bridge.addresses.UIScrollReturn`
records the preferred return PC `0xe8ed8f0` after the UI's virtual scroll-getter
call at `0xe8ed8ec`. BaseInput.get_mouseScrollDelta tail-branches to Unity's wrapper, but the wrapper
itself calls the native callback with BLR and saves x29/x30. The initial correction
incorrectly checked the immediate return PC and did not normalize menu reads.
Runtime diagnostics verified that immediate PC is `0xe89c508`, now recorded as
`ScrollWrapperReturn`. Only when that exact wrapper is present does the callback
read its parent return PC to identify the UI callsite. The legacy callback
normalizes only that caller by `scroll_units_per_step`; gameplay retains its
confirmed zoom scale. Synthetic tests verify both callers can read the same
frame without consuming or rescaling each other's state. Runtime startup now logs that the UI caller was verified and normalization
is active. The user confirmed reasonable menu speed and working camera zoom on 2026-11-01.
