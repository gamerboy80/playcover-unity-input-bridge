# ZZZ PC controls on Apple Silicon

Enables the existing PC control path in Zenless Zone Zero's iOS build running
under PlayCover, then bridges macOS keyboard and mouse events into Unity's
Input System. This uses native Unity devices, rather than touch keymapping.

**Supported build:** ZZZ 3.3.0, bundle `com.HoYoverse.Nap`, with UnityFramework
SHA-256 `8514f6ecf03272586a5c722db0d407608b5b28e9815b046e7b3f71ce588ee037`.
The installer refuses other binaries. An update to the game requires new analysis;
do not reuse these addresses on another build.

## Build and install

Requires Apple Silicon macOS, Python 3.9+, and Apple's Command Line Tools with
the macOS SDK and Catalyst UIKit headers. Full Xcode is not required.
Supply your own installed, decrypted game. No game binaries are distributed here.

Quit the game, then run:

```sh
python3 patch.py install
```

The default app location is
`~/Library/Containers/io.playcover.PlayCover/Applications/com.HoYoverse.Nap.app`.
For another location:

```sh
python3 patch.py install --app '/path/to/Zenless Zone Zero.app'
```

The script builds and signs the bridge, checks the exact original framework hash,
backs up the original framework/executable/signatures in `.local/`, applies the version-locked
PC input selector patch, links the bridge using unused executable header
padding, and signs/verifies the app. Keep `.local/` for restoration. Avoid running
two installer commands at once. Restore any earlier experimental patch first.

## Controls

- Disable PlayCover **keymapping**; an empty keymap alone still enables its handlers.
- The game requests mouse capture natively. **Option+M** is an optional fallback
  toggle; **Escape** releases manual capture.
- WASD, key releases, F1–F12, mouse look, buttons, and both scroll axes are forwarded.
- Trackpad/Magic Mouse movement accumulates independently on each axis. Every
  **16 points** emits one standard **120-unit wheel step**; leftover movement
  carries into the next event. Each emitted step is also converted into a normal,
  non-precise AppKit line-wheel event, preserving its location and targeting the
  active game window. It is freshly created, without copied gesture metadata.
  The original gesture is consumed and the wheel event is queued inside the app
  to re-enter the ordinary wheel handler once.
  A new gesture or focus loss clears the remainder.
  Physical notched wheels remain immediate. The game's original mouse component
  processes scrolling against the current bridge Mouse, including login settings.
- Losing application focus releases held input and mouse capture. Command shortcuts
  remain available to macOS. On Apple keyboards, F-keys may require Fn/Globe.

Build only, update an existing installation, inspect, or restore:

```sh
python3 patch.py build
python3 patch.py update
python3 patch.py status
python3 patch.py restore
```

Use the same `--app` when needed. Updates verify installed hashes before changing
files. Restore reinstates original bytes and signature resources and removes the
bridge. It refuses to overwrite an app changed since installation. Backups remain
after restoration; archive `.local/` before starting a fresh installation.

## Validation and limits

```sh
sh tests/run.sh
```

The tests cover exact instruction edits, Mach-O load-command padding and rejection
of unsafe headers, wheel/trackpad conversion, threshold/remainder/direction behavior,
full-size Mouse state padding, and actual AppKit event conversion. The native
event test checks that a precise gesture becomes a non-precise wheel with the
expected notch counts while preserving its location, then survives an AppKit
queue/dequeue cycle without becoming precise again. With WindowServer access,
it also checks destination-window binding after dequeueing. That check is skipped
in a headless sandbox. Builds enable warnings as errors
and assert Unity event layouts. Keyboard, WASD release, F1/F2, mouse look, and
capture/release were confirmed in a physical gameplay test before the scroll update.
The scroll update passes configuration loading with the original mouse component
enabled, and graphics-list scrolling was visually verified with a wheel event.
Physical trackpad testing is still in progress.
See [analysis notes](docs/analysis.md) for the loading fix and runtime evidence.

The bridge is experimental and version-specific. Chat/IME, non-US layouts, other
mouse hardware, and coexistence with PlayTools have not been fully tested. Game
updates or PlayCover re-signing can invalidate recorded hashes. No server behavior
or account-safety guarantees are established by these local tests.

Logs contain device setup and capture status, not keystrokes:
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
