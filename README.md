# Native Unity PC controls on Apple Silicon

Enables the existing PC control path in Zenless Zone Zero's iOS build running
under PlayCover, then bridges macOS keyboard and mouse events into Unity's
Input System. This uses native Unity devices, rather than touch keymapping.

**Examined build:** ZZZ 3.3.0, bundle `com.HoYoverse.Nap`, defined in
[`profiles/com.HoYoverse.Nap-3.3.0.json`](profiles/com.HoYoverse.Nap-3.3.0.json). Each game/build profile lists
its exact original framework hash, named byte patches with expected/replacement
bytes, runtime addresses, field offsets and validation status. The installer
refuses other binaries. An update to the game requires new analysis.

See [porting instructions](docs/porting.md) to add a version or another compatible
Unity game, and [AGENTS.md](AGENTS.md) for repository architecture and development
rules. HSR 4.6.0 also has an experimental [`hsr` profile](profiles/com.HoYoverse.hkrpgoversea-4.6.0.json)
using the legacy Unity/InControl backend. An explicit test-only profile changes only
HSR's app-level platform mapping to PC; it is excluded from automatic profile selection.
See [HSR status and analysis](docs/hsr.md).

## Build and install

Requires Apple Silicon macOS, Python 3.9+, and Apple's Command Line Tools with
the macOS SDK and Catalyst UIKit headers. Full Xcode is not required.
Supply your own installed, decrypted game. No game binaries are distributed here.

Quit the game, then run:

```sh
python3 patch.py install
```

List profiles or select one explicitly:

```sh
python3 patch.py profiles
python3 patch.py build --profile zzz-3.3.0
python3 patch.py install --profile zzz-3.3.0
python3 patch.py install --app '/path/to/com.HoYoverse.hkrpgoversea.app'
```

`com.HoYoverse.Nap-3.3.0` remains the default without `--app`.
Profile filenames are `<bundle-id>-<version>.json`; `--app` automatically selects
by bundle ID, version and executable. Unknown versions, ambiguous matches, and
explicit mismatches are rejected. Installation also requires the exact original
framework hash. The old `zzz-3.3.0` and `hsr` names remain aliases and existing
backup locations are preserved. Builds generate `build/<profile-id>/Profile.h`
from JSON and compile a matching `NativeInputBridge.dylib` in that directory.
The profiles share macOS input/capture handling and select different game-facing
backends. HSR builds and backups are independent of ZZZ.

ZZZ also has an explicit test-only profile that overrides Unity's managed
`Application.platform` result to `WindowsPlayer` to exercise the broader PC
platform path. It is excluded from automatic profile selection; see the test
notes in [analysis](docs/analysis.md).

The default app location is
`~/Library/Containers/io.playcover.PlayCover/Applications/com.HoYoverse.Nap.app`.
For another location:

```sh
python3 patch.py install --app '/path/to/Zenless Zone Zero.app'
```

The script builds and signs the bridge, checks the exact original framework hash,
backs up the original framework/executable/signatures in `.local/<profile-id>/`, applies the version-locked
PC input selector patch, links the bridge using unused executable header
padding, and signs/verifies the app. Keep `.local/` for restoration. Avoid running
two installer commands at once. Existing pre-profile backups in `.local/` remain
usable when their original hash matches. Restore any earlier experimental patch first.

## Controls

- Disable PlayCover **keymapping**; an empty keymap alone still enables its handlers.
- The game requests mouse capture natively. **Option+M** is an optional fallback
  toggle; **Escape** releases manual capture.
- When capture starts with the pointer outside the content area (for example,
  after clicking the Dock icon), the bridge moves it into the game before locking
  it. A pointer already inside stays in place.
- WASD, key releases, F1–F12, mouse look and buttons are forwarded. Physical
  trackpad scrolling was confirmed by the user after the legacy mouse-presence fix.
- Trackpad/Magic Mouse movement accumulates independently on each axis. Every
  **16 points** emits one standard **120-unit wheel step**; leftover movement
  carries into the next event. Each emitted step is also converted into a normal,
  non-precise AppKit line-wheel event, preserving its location and targeting the
  active game window. It is freshly created, without copied gesture metadata.
  The original gesture is consumed. A main-queue callback processes the ordinary
  wheel event once and delivers it to the native view under the cursor, with
  an explicit game-window binding.
  A new gesture or focus loss clears the remainder.
  Physical notched wheels remain immediate. The game's original mouse component
  processes scrolling against the current bridge Mouse, including login settings.
- Unity's legacy `Input.mousePresent` callback also reports the validated bridge
  Mouse. Without this, the iOS player reports no mouse and the UI skips mouse
  processing even though the new Input System receives scroll events.
- Losing application focus releases held input and mouse capture. Command shortcuts
  remain available to macOS. On Apple keyboards, F-keys may require Fn/Globe.

Build only, update an existing installation, inspect, or restore:

```sh
python3 patch.py build
python3 patch.py update
python3 patch.py status
python3 patch.py restore
```

Use the same `--profile` and `--app` when needed. Updates verify installed hashes before changing
files. Restore reinstates original bytes and signature resources and removes the
bridge. It refuses to overwrite an app changed since installation. Backups remain
after restoration; archive that profile's local directory before a fresh install.
Restore before updating the game. The `update` command updates this patch for the
same exact game binary; a new game version needs a newly analyzed profile.

## Validation and limits

```sh
sh tests/run.sh
```

The tests cover profile validation/header generation, backup isolation and legacy
state compatibility, mouse-presence callback fallback/idempotence,
synthetic install/update/signing-failure rollback/restore,
exact instruction edits, Mach-O load-command padding and rejection
of unsafe headers, wheel/trackpad conversion, threshold/remainder/direction behavior,
full-size Mouse state padding, and actual AppKit event conversion. The native
event test checks that a precise gesture becomes a non-precise wheel with the
expected notch counts while preserving its location, then survives an AppKit
queue/dequeue cycle without becoming precise again. With WindowServer access,
it also checks destination-window binding, hit testing, and delivery to the
native view's `scrollWheel` handler. Window checks are skipped
in a headless sandbox. Builds enable warnings as errors
and assert Unity event layouts. Keyboard, WASD release, F1/F2, mouse look, and
capture/release were confirmed in a physical gameplay test before the scroll update.
The scroll update passes configuration loading with the original mouse component
enabled, and graphics-list scrolling was visually verified with a wheel event.
Physical trackpad scrolling was confirmed by the user on 2026-11-01 after bridging
the legacy mouse-presence callback. Earlier versions through `61cce82` received
scroll state but failed in the UI. Camera zoom and other wheel hardware have not
been separately confirmed.
See [analysis notes](docs/analysis.md) for the loading fix and runtime evidence.

The bridge is experimental and version-specific. Chat/IME, non-US layouts, other
mouse hardware, and coexistence with PlayTools have not been fully tested. Game
updates or PlayCover re-signing can invalidate recorded hashes. No server behavior
or account-safety guarantees are established by these local tests.

Logs contain device setup, capture status and up to 30 aggregate scroll diagnostic
lines (at most one per second), not keystrokes or scroll coordinates:
`~/Library/Containers/com.HoYoverse.Nap/Data/Documents/LogDir/NativeInputBridge.log`.

## PlayTools window and scaling fixes

PlayTools initializes window/display fixes separately from keymapping. However,
it unconditionally overrides Unity's pointer-lock preference. The optional
[PlayTools source patch](patches/playtools-native-pointer-lock.patch) gates that
override on keymapping being enabled. It was prepared against PlayTools commit
`48d7b1f` (already integrated in `e7b636c`); it is not automatically installed
by this project.

```sh
git -C /path/to/PlayTools apply /path/to/zzz-pc-mac-patch/patches/playtools-native-pointer-lock.patch
```

Keep `disableBuiltinMouse=false`. PlayTools' per-frame main-queue workaround remains
active even with mapping off; its effect with this bridge is unmeasured.

Build outputs, game backups, installation state, and local logs are ignored by Git.

The optional PlayTools patch includes context from PlayTools, covered by the
[PlayTools AGPL-3.0 license](patches/PlayTools-LICENSE).
