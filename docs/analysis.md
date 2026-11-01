# Analysis of the supported 3.3.0 build

The machine-readable source for byte patches, VM addresses and object/static
offsets is [`profiles/zzz-3.3.0.json`](../profiles/zzz-3.3.0.json). The shared
bridge consumes a header generated from that profile. See [porting](porting.md)
for the ABI contract and the process for adding another build.

The decrypted arm64 UnityFramework exposes an IL2CPP PC layout/input path even
though the packaged player is an iOS build converted for Catalyst by PlayCover.
The obfuscated layout selector at `0xc22d6b8` returns an enum whose PC value is 2.
Changing its entry to `mov w0,#2; ret` makes the game display PC control prompts
and enables its keyboard path.

That patch alone stalled configuration loading. Three local launch logs reported
`NullReferenceException` from `Foundation.MouseInputEnhancement.InitAllState`.
The throw at `0xb0a4ffc` follows a null position-control check at `0xb0a4aa8`.
Restoring original files restored loading. This is evidence of a local startup
failure; the examined logs did not establish server detection or rejection.

An earlier workaround made `MouseInputEnhancement.get_EnabledOnPlatform` at
`0xb0a6274` return false. That restored loading, but also disabled the game's
scroll accumulation. The final implementation creates a complete Mouse before
configuration loading and keeps the original enhancement component enabled.
Its startup log confirms initialization without the original exception. Only
the eight-byte PC selector remains patched in UnityFramework.

A temporary read-only probe found that GameController reported a keyboard and
mouse, while Unity had a current keyboard and no current mouse during its 120
samples. The probe was removed after diagnosis. A separately linked native bridge
then created Mouse and Keyboard layouts through this build's InputSystem and
fed StateEvents from app-local AppKit monitors. Runtime validation found non-null
mouse position/delta controls. Capture/release and the combined physical keyboard,
WASD-release, F1/F2 and mouse-look test succeeded.

## Native bridge addresses

All are preferred UnityFramework VM addresses, relative to its zero preferred
base; the bridge adds the loaded image's slide. They are valid only for the exact
hash enforced by the installer.

| Address or offset | Purpose |
| --- | --- |
| `0x1c69e278` | Managed static-storage pointer |
| static `+0x2ae78` | InputManager |
| static `+0x2b2c0`, `+0x2b4c0` | Current Keyboard and Mouse |
| `0x133ade68` | Mouse.MakeCurrent |
| `0xb0a61d4` | Enable original mouse processing after device validation |
| `0x13a84cb0` | UTF-8 IL2CPP string creation with explicit length |
| `0x133fa120` | InputSystem.AddDevice(layout, name, variants) |
| device `+0x144` | Device ID |
| mouse `+0x178`, `+0x170` | Position and delta controls |
| `0x138d66b4`, `0x138d66f0` | Native input time and event queue |
| `0x1389069c`, `0x138906ac` | Screen width and height |
| `0x1380e1c8`, `0x1380e1a8` | Unity cursor lock and visibility |

The event header uses a 20-byte NativeInputEvent plus a four-byte state format.
The standard MouseState prefix is 30 bytes, with scroll X/Y at offsets 16/20.
This build's FastMouse appends controls to a 49-byte device state. The bridge
validates the live MOUS format and state size, zero-pads the event to that size,
and rejects unexpected layouts. Keyboard state is a
14-byte bitset. The native source has layout assertions and a verified key table.
Unity accumulates mouse scroll events and resets scroll during the next update.
The bridge clears its transient values after each queue operation.

References for the public event layouts and accumulation behavior:

- [Unity NativeInputEvent](https://github.com/Unity-Technologies/UnityCsReference/blob/master/Modules/Input/Private/Input.cs)
- [Unity Input System 1.3 MouseState and Mouse](https://github.com/Unity-Technologies/InputSystem/blob/1.3.0/Packages/com.unity.inputsystem/InputSystem/Devices/Mouse.cs)

The repository contains authored patch code and notes. Proprietary game files,
metadata dumps, disassembly, personal paths, and runtime account logs are excluded.

## Scrolling

Raw 30-byte events did not produce a nonzero scroll control in the examined
runtime test. Matching the live 49-byte Mouse state did. The bridge also makes
its Mouse current before queueing events, so the original mouse enhancement
component compares scroll controls from the correct device. Native scroll
processing is preserved rather than bypassed with a game-action patch.
Both axes accumulate precise trackpad deltas until 16 points produce a standard
120-unit wheel event. A fresh native line-scroll CGEvent becomes a non-continuous
AppKit wheel event, preserving the source location and targeting the game window.
Trackpad gesture metadata is not copied. It is scheduled on the main queue
after the gesture callback, processed once through the ordinary wheel handler,
and delivered to the hit-tested native view's scrollWheel handler; the original
precise event is consumed, avoiding recursive conversion or duplicate delivery. Fractions carry forward; gesture start/cancel and focus loss
clear the remainders. A scroll event without a window can use the active
application's key window. The original mouse component is enabled after the
bridge validates its Mouse, rather than waiting for game-asset loading, so the
login/settings screen has the same mouse processing.

Scrolling the graphics settings list was visually verified with an injected wheel
event. Physical trackpad verification is tracked separately; a working injected
wheel alone does not establish trackpad support. Status logging reports the first
local/precise scroll event and first nonzero Unity scroll state without recording
scroll values or keystrokes. The unused legacy and direct-reader experiments
were removed.

AppKit's public CGEvent window-under-pointer fields do not bind `NSEvent.window`.
A native runtime test found window number 0 on a fresh wheel event.
`_eventRelativeToWindow:` binds it to the target NSWindow, but queue/dequeue can
discard that binding. The ordinary wheel handler therefore reapplies the binding
after dequeueing, before returning the event for UI dispatch. A WindowServer-backed
test verifies this routing sequence with an invisible test window. The private
selector is checked at runtime; its availability is an OS compatibility constraint.

Production dispatch retains the bound NSEvent in a main-queue callback rather
than relying on implicit monitor re-entry through NSApplication.postEvent. The
callback processes its coarse event once, binds it to the game window, hit-tests
the window's content view and invokes the native target's scrollWheel handler.
The WindowServer-backed regression test verifies that the real target NSView
receives the correct coarse deltas through this same helper.

The user reported **still no physical trackpad response with `61cce82`**. This
invalidates any inference that direct native-view dispatch solved the gameplay
problem. The event conversion and view-dispatch self-checks pass, while the actual
trackpad-to-game path remained unresolved at that point. The profile refactor changes how these
constants are supplied; it does not claim to fix scrolling.

## Confirmed mouse-presence fix

A bounded diagnostic on physical gestures recorded hundreds of precise AppKit
events, thresholded wheel events, nonzero bridge Mouse scroll, and nonzero
`MouseInputEnhancement.CurrentScrollDelta`. The processor was enabled and the
bridge Mouse was current. GameController had one mouse but no registered wheel
or axis callbacks; forwarding to an existing callback was therefore not applicable.

Legacy `Input.mousePresent` still returned false. Native disassembly showed
`StandaloneInputModule.Process` checking its BaseInput mouse-present getter before
calling `ProcessMouseEvent` (`0x13933864` call, `0x13933868` conditional branch).
Consequently the UI did not consume the already accumulated scroll. A trial NOP
of that branch was insufficient and was removed; this game also has hotfix dispatch
before the native body. Do not retain that unsuccessful instruction patch.

The getter at `0x138d4d8c` tail-calls the native function pointer at preferred VM
`0x1c693fe0 + 0x6f18 = 0x1c69aef8`. The bridge now saves that callback and replaces
it in writable data after validating its Mouse. It returns true while ready and
otherwise delegates to the original. Installation is idempotent to avoid saving
the bridge as its own fallback. No additional framework instruction patch is used.

The resulting runtime reported `legacyMousePresent=1`, with the callback called
throughout UI updates. Physical gestures produced matched nonzero control and
processed-scroll samples, and the user confirmed: "Wow it works now" on
2026-11-01. This is physical confirmation of the current scroll fix; camera zoom
and other mouse hardware have not been independently tested. Diagnostics are
bounded to 30 aggregate lines, at most one per second, without input coordinates.

## Capture after Dock activation

The user reported a frozen pointer after activating the game from the Dock while
the cursor was outside its window; switching with the pointer inside worked.
The bridge previously disconnected mouse/cursor association immediately when
Unity requested capture. An outside cursor could then remain fixed outside the
window, preventing app-local mouse events from reaching the game.

On capture entry, the bridge now checks the cursor in content-view coordinates.
If outside, it converts the content center through window and screen coordinates,
flips the AppKit Y coordinate against the primary display's top edge, and uses
CGWarpMouseCursorPosition before disconnecting association. This API does not
generate a synthetic movement event. An inside cursor is left alone. Missing
window/geometry defers capture; a failed warp restores association instead of
locking outside. Geometry tests cover Dock positions, edges, empty content and
displays above/left of the primary. Physical Dock reactivation awaits confirmation.

The user confirmed initial Dock capture worked, then reported intermittent visible
cursor/capture failures and a first-motion camera jump. Capture now waits 150 ms
after activation while restoring association, allowing native focus handlers to
settle before recapturing. During capture, a visible Quartz cursor is hidden again
without blindly incrementing the hide count every frame. The first movement sample
and samples in the first 100 ms of capture are discarded so cursor repositioning
cannot become a camera delta. Tests cover delayed first movement and subsequent
settled samples. Physical confirmation of this follow-up remains pending.
