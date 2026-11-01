# Working on this patch

This repository enables a game's existing PC input path and feeds native macOS
events into its IL2CPP Unity Input System under PlayCover. It is an experimental,
exact-build patcher. Read `README.md`, `docs/porting.md`, the selected profile, and
`docs/analysis.md` before changing address-dependent behavior.

## Where things live

- `profiles/*.json`: one immutable build identity per game/version/binary hash;
  named instruction edits with expected/replacement bytes; preferred VM addresses;
  managed-object/static field offsets; mouse payload size; physical-test status.
- `profiles.py`: validates profiles and generates `build/<id>/Profile.h`.
  It contains the supported backend contract's required constant names.
- `src/NativeInputBridge.m`: shared AppKit event monitoring, Unity device setup,
  keyboard/mouse state queueing and capture. It consumes named generated constants.
  `InputState.h`, `Scroll.h`, `NativeWheel.h`, and `MousePresence.h` hold shared handling.
- `patch.py`: identity/hash guards, byte edits, Mach-O library linking, originals,
  signing, rollback, status and restore. `build.sh` builds a profile-specific dylib.
- `patches/`: optional PlayTools source changes, separate from game byte patches.
- `tests/`: synthetic installer/profile tests and native event self-checks.

## Rules for ports and edits

1. Add a new profile for a new binary; never relax a hash check or replace an old
   profile's hash to make a different build pass. Reuse a JSON profile only when
   the shared backend's ABI and layouts have actually been established.
2. Keep game/version addresses, managed field offsets and byte patches in the
   profile. Put explanations and calling-convention evidence in analysis notes.
   Do not scatter game-name conditionals or new magic addresses through the bridge.
   If another game requires a different ABI or processing algorithm, implement and
   test that backend explicitly; configuration alone does not make it supported.
3. Patch locations are **file offsets**. Bridge addresses are **preferred VM
   addresses**, added to the dyld slide. Object/static offsets are a third kind.
   Convert using Mach-O segments; do not assume VM address equals file offset.
4. Preserve exact expected bytes, equal replacement lengths, non-overlapping edits,
   untouched executable sections, entitlements, existing PlayTools load commands,
   original backups, installed-hash checks, execute permissions and failure rollback.
   Never delete `.local/` as cleanup. Do not overwrite an independently modified app.
5. Building and testing this repo does not require reinstalling or restarting the
   real game. For an installation task, require a closed game and use the installer.
   Do not run overlapping installers or leave disassembly/symbol jobs running;
   inspect bounded address ranges instead of unbounded `nm` output.
6. Do not commit proprietary game binaries, metadata/disassembly dumps, installation
   backups, build output, account logs, personal paths or credentials. Keep those
   local and ignored. Preserve the PlayTools license alongside its source patch.

## Validation

Run `sh tests/run.sh` and `python3 patch.py build --profile <id>` after relevant
code changes. A sandbox without WindowServer skips native window/view checks;
report that skip. Signing is real for the built dylib; installer tests mock signing
and use synthetic bundles, so they do not establish a real-game installation.

For a new port, verify the original framework hash and expected bytes, inspect the
generated header, build with warnings as errors, then perform the staged runtime
checks in `docs/porting.md`. Record physical hardware tests separately from
synthetic event tests. Do not infer hardware success from nonzero Unity state.

## Current known state

Only ZZZ 3.3.0's listed arm64 binary has been analyzed. Keyboard, WASD release,
F1/F2, mouse look and native capture were confirmed earlier. PlayTools is retained
with keymapping off; Option+M is an optional capture fallback.

**Physical trackpad scrolling was confirmed working by the user on 2026-11-01**
after bridging the legacy `Input.mousePresent` callback. The iOS player returned
false despite a valid bridge Mouse and nonzero scroll state. StandaloneInputModule
checks that legacy flag before processing mouse events. Preserve the profile's
`LegacyMousePresentSlot` hook and its original-callback fallback; the hook is
installed once after device validation. Earlier threshold/window/view fixes
through `61cce82` were insufficient. Camera zoom and other hardware are unverified.
A synthetic wheel event moving a list is separate evidence from physical input.

The original config-loading failure was a local null Mouse control exception.
Creating a valid Mouse before enabling the original game's mouse processing
avoided it. The current game profile patches only the PC selector; do not restore
the earlier blanket mouse-processing-disable patch as part of a port.
