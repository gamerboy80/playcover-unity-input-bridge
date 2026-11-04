# Arknights: Endfield 1.6.3

Experimental profile `com.gryphline.endfield.ios-1.6.3` (alias `endfield`), bundle
`com.gryphline.endfield.ios`, executable `Endfield`. Explicit selection is required.

Framework SHA-256:
`767616ee9093e7ce8a588f30ed4beef3929d4adb0fcfb8ca100e7b8a77d4cb13`.
The framework is a decrypted thin arm64 image. IL2CPP metadata reports version
29; examined type rows are 92 bytes and method rows 32 bytes. Image records map
method tokens to code-generation module method tables. Chained-fixup pointers
in the examined tables carry high encoding bits; the recovered target occupies
the low 36 bits and was checked against disassembly.

Unity InputLegacyModule exposes ordinary internal-call wrappers. Each caches
its callback in writable memory under VM page `0x176e9000`, resolves a full
internal-call name through `0x1111bdac`, then tail-calls the cached callback.
Position and scroll injected getters pass caller-owned float arrays. Key and
button getters accept integer codes; axes accept managed UTF-16 strings.
All callback addresses in the profile were recovered from these wrappers.

The legacy bridge waits for at least one populated callback, then resolves
unused callbacks through the non-throwing registry lookup at `0x1113bdf8`.
The wrapper's `0x1111bdac` entry throws on lookup failure and caused an early
startup crash when called before Unity registered its callbacks. It is not used
by the bridge. Missing registry entries keep initialization pending without
installing partial hooks. Other profiles default to the existing
initialization path. UI-specific scroll return addresses are disabled because
no corresponding Endfield caller normalization has been verified. Wheel scale
is provisionally one Unity unit per step.

The legacy bridge-only and provider-selection tests received physical keyboard
events and returned positive key results, but no gameplay input worked. A live
memory check found a non-null Input System Keyboard, a null Mouse, and input
mode `1` (touch). `InputManager.GetKey` uses Input System controls when that
Keyboard exists, bypassing the legacy getter for mapped keys.

The current profile uses the Input System event backend with the legacy
supplement enabled. Endfield keeps statics
in separate IL2CPP classes, unlike ZZZ's shared static-storage region:

| Identity | Class-reference VM address | Static member |
| --- | --- | --- |
| InputSystem | `0x16e46670` | manager at `+0x8` |
| Keyboard | `0x16e477a0` | current at `+0x0` |
| Mouse | `0x16e4a608` | current at `+0x0` |

The class static-storage pointer is at `+0xb8`. Unresolved references contain
odd metadata tokens and must not be dereferenced; an early test crashed before
this guard was added. The bridge waits for resolved storage and an initialized
manager/Keyboard. These references were checked against getters and live memory.

The native ABI was checked against the following methods:

- `il2cpp_string_new_len` at `0x110f8c8c`: managed UTF-8 strings with length.
- `InputSystem.AddDevice` at `0x1039e4a0`: layout/name/variants strings.
- `Mouse.MakeCurrent` at `0x103b1800`: mouse instance.
- Native input time and event queue at `0x1072a904` and `0x1072a9a0`.
- Device ID at `+0xe0`, state block at `+0x10`, position at `+0x188`,
  delta at `+0x190`, and scroll at `+0x1b8`.

The live Mouse reports `MOUS` and **49 bytes**. The initial 30-byte assumption
was rejected by the layout check; the profile now uses the measured size.
`ReadVector2` diagnostics remain disabled until their generic-method ABI is
verified. No successful gameplay claim follows from device creation alone.

The profile also includes narrowly scoped framework edits:

- `LocalDeviceInfoProvider.get_initialInputType` (`0x2c5b010`) returns keyboard
  enum `0`. This is independently established by `DeviceInfo.get_usingKeyboard`
  (`0x2c5bf08`), which compares its inputType field to zero. Touch is `1` and
  controller is `2`.
- The keyboard-only path of `SupportsInputType` (`0x2c5b094`) returns true
  rather than tail-calling `DeviceInfo.get_isPCorConsole`. Its stack restoration,
  touch/controller handling and invalid-type rejection remain intact.
- `DeviceInfo.Init` inlines the initial-input getter in its local-provider branch
  at `0x2c5c560`. Patching the getter alone missed this assignment. This site
  now loads keyboard enum `0` into `w19`; live memory confirms input mode `0`
  after initialization.

Platform enums, graphics settings and renderer behavior retain original values.
The game also includes Rewired and Unity Input System assemblies;
legacy callback availability alone does not prove gameplay uses those callbacks.
Gameplay backend selection, PC layout, capture, sensitivity and scrolling all
require runtime evidence. Global DeviceInfo platform predicates must not be
changed merely to force keyboard UI: their graphics/network callers remain
unreviewed.

The Input System bridge initializes a valid 49-byte Mouse and Keyboard and
installs its local event monitor. Physical WASD movement works and capture
engages, but camera motion failed in the Input System-only test.
`InputManager.GetMousePos` falls back to legacy mouse position in keyboard mode;
its scroll getter also falls back to the legacy API. The combined test still
failed camera look and introduced duplicate menu clicks. Legacy button injection
is now disabled (`legacy_buttons: false`), preserving native UI clicks while
keeping other legacy readers available. Axis-label/caller diagnostics are
bounded to eight distinct configuration labels, with no key contents logged.
Mouse look, scrolling and the click correction require validation. Earlier
legacy-only builds failed physical tests despite
positive callback counts. The synthetic suite
includes flat/per-class storage, null storage, unresolved metadata references
and profile validation; builds treat warnings as errors.

Axis diagnostics identified `MouseAxis1`, `MouseAxis2` and `MouseAxis3`, all
requested from `0xf890148` in Rewired's three-axis polling loop. The installed
`globalgamemanagers` InputManager records independently map these names to
mouse X (axis 0, descriptions `Mouse +X` / `Mouse -X`), mouse Y (axis 1), and
wheel (axis 2). The profile's `legacy_axes` maps these verified labels to the
shared bridge's X, Y and scroll state. The original canonical names remain
supported for other readers. Earlier combined builds returned the original
zero axis values because only the canonical names matched.

Build and install with `python3 patch.py apply --profile endfield --app APP`.
Restoration uses the normal independent installer and preserves other registered
bridges. Disable PlayCover keymapping for physical native-input validation.

The axis aliases matched live Rewired reads, but physical camera look still
failed. A dropdown also opened and closed on a single button cycle, even with
legacy button injection disabled. Endfield now routes uncaptured button
sequences exclusively through the host UI. Capture requests mouse-moved events
on the game window and routes windowless motion only to the active game window.
The `nonzeroAxes` counter distinguishes motion samples from idle axis reads.
Physical camera motion and dropdown behavior need validation on this build.

Physical testing confirmed the revised menu click routing. Rewired consumed
nonzero axes during capture, yet the camera did not turn. Its mouse poll reads
Unity's position at return address `0xf890194`. Rewired's
`Mouse.get_screenPositionDelta` subtracts consecutive positions. The bridge now
accumulates relative motion for that poll only, identified through Unity's
wrapper return at `0x10728c68`. In-game camera response is pending.

The scoped position experiment also failed physical testing and was removed.
A bounded live trace observed Rewired polling but no call to
`CameraManager.OnInput`, `LevelCameraController.OnInput` or the Rewired
position-delta getter during the physical movement test. The current adapter
forwards captured motion directly to `CameraManager.OnInput` at `0x35187a8`,
whose native ABI is `void(manager, float x, float y, MethodInfo*)`. It dispatches
to the active controller, which retains camera input suppression and module
checks. The manager is obtained from the resolved class at `0x16e42248`,
static storage `+0xb8`, member `+0x30`, as verified in
`CameraUtils.get_cameraManager`. Movement is normalized by screen width/height.
Delivery requires capture and Unity's own lock state 1. Physical camera behavior
and sensitivity remain pending.


Physical testing on 2026-11-03 confirmed camera look and reasonable speed with
direct camera forwarding. WASD, pointer capture and menu clicks were also
confirmed. The profile remains experimental. Physical scrolling, broader button
coverage, focus transitions and extended gameplay still need validation.

Trackpad scrolling responds physically. Momentum after finger release was
reported during validation. The shared event handler now consumes every AppKit
momentum phase before conversion or native forwarding. Direct gestures still
produce discrete wheel steps, with fractional remainders cleared on gesture end
or cancellation. Synthetic tests cover momentum begin/change/end, gesture
termination, and the following direct gesture. Physical stop timing needs
confirmation on the updated build.
