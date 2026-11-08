# Contributor and automation guide

This repository contains exact-build input bridges and patch profiles for
selected Unity games running under PlayCover. Changes to native addresses,
object layouts or instruction bytes require evidence from the target game build.

Before changing address-dependent behavior, review the [README](README.md),
[porting guide](docs/porting.md), selected profile and relevant analysis notes.

## Repository layout

- `profiles/*.json`: game/build identity, original binary hash, named byte
  patches, preferred VM addresses, object fields and validation status.
- `profiles.py`: profile validation and generation of
  `build/<profile-id>/Profile.h`.
- `signatures.py`, `signatures/*.json`: metadata discovery, native signatures,
  field extraction and cross-checks for automatic version detection. Generated
  profiles and resolution evidence stay under `.local/profiles/`.
- `src/NativeInputBridge.m`: shared AppKit event monitoring, Unity device setup,
  keyboard/mouse state queueing and cursor capture.
- `src/LegacyBackend.h`: legacy Unity input backend used by HSR and the
  initial Endfield research builds.
- `src/InputSystemStatics.h`: flat or per-class static storage for Input System
  devices. Endfield uses separate IL2CPP class storage; ZZZ uses flat storage.
- `src/InputState.h`, `src/Scroll.h`, `src/NativeWheel.h` and
  `src/MousePresence.h`: shared event and state handling.
- `src/EventRouting.h`: game-window and native text-responder filtering.
- `src/EventHandler.h`: shared event dispatch, input release and modifier handling;
  tested with fake host events and backend callbacks.
- `patch.py`, `build.sh`: profile selection, binary editing, Mach-O linking,
  signing, backup, rollback, status and restoration.
- `patches/`: optional PlayTools source changes, separate from game profiles.
- `tests/`: synthetic installer/profile checks and native event checks.
- `macho.py` and `bridge_registry.py`: shared Mach-O dylib ownership and
  install state, kept compatible with the ZZMI Metal repo's copies.

## Profile and binary invariants

1. Create a new profile for each new game binary. Automatic resolution must
   recover and verify its methods and fields before recording the exact new
   framework hash. Never reuse addresses or fields solely because bytes or a
   prologue look similar. Missing or ambiguous matches must stop resolution.
2. Keep build-specific addresses, field offsets and byte edits in JSON profiles.
   Record function mapping, calling conventions and disassembly evidence in the
   relevant analysis document.
3. Treat file offsets, preferred VM addresses and object/static offsets as
   distinct values. Use Mach-O segment mappings; do not assume they are
   interchangeable.
4. Every patch must record exact expected and replacement bytes of equal length.
   Reject overlapping or unaligned edits. Preserve all unpatched executable
   sections, entitlements, existing PlayTools load commands and executable
   permissions.
5. Keep installer hash checks, backup isolation, installed-file checks, rollback
   and signature verification intact. Do not overwrite an independently changed
   app. Never remove `.local/` as routine cleanup.
   Record original and planned file hashes before app writes. Interrupted
   recovery may accept either recorded version, but must reject unknown files.
6. Test-only profiles require explicit selection and must remain excluded from
   automatic app matching.
7. Keep bridge load commands independently owned. Restoring the native input
   patch must preserve `ZZMIMetal.dylib` and update the shared registry. Keep
   `macho.py` and `bridge_registry.py` synchronized with the ZZMI Metal repo.
8. Do not commit proprietary binaries, metadata or disassembly dumps, runtime
   account logs, installation backups, build output, personal paths or
   credentials. Retain the license notice for the optional PlayTools patch.
9. The root MIT license covers original project files. Honor separate
   third-party license notices; do not relicense the PlayTools patch.

## Build and validation

Run the relevant checks after implementation changes:

~~~sh
sh tests/run.sh
python3 patch.py build --profile <profile-id>
~~~

Builds use warnings as errors and verify the generated bridge layout. Native
window/view checks require WindowServer access and are skipped in headless
environments. Installer tests use synthetic app bundles and mocked signing;
they do not validate installation into a real game.

For a new profile, verify the original framework hash and every expected byte
range, inspect the generated header and complete the staged runtime checks in
the [porting guide](docs/porting.md). Record hardware outcomes separately from
synthetic event results. Nonzero input state alone does not prove gameplay
behavior.

Close the target game before installation, update or restoration. Do not run
overlapping installer operations or leave disassembly jobs running. Keep
disassembly bounded to relevant address ranges.

## Implemented profiles

- ZZZ 3.3.0 uses the Unity Input System backend. Keyboard, mouse capture/look
  and physical trackpad scrolling have been validated. Its app-level PC/settings
  profile is experimental.
- ZZZ 3.3.1 has separately verified native addresses and changed object fields.
  Launch, device initialization and purchase-slider routing have been checked.
  The category-filter correction restores keyboard binding labels and controls;
  changed-binding persistence still needs verification. The automatic resolver reproduces both
  reviewed 3.3.1 profiles; future versions are not automatically runtime validated.
- HSR 4.6.0 uses the legacy Unity/InControl backend. Keyboard movement, mouse
  capture/look, camera zoom, menu cursor visibility and menu scrolling have been
  validated. Broader button coverage and the PC/settings profile remain
  experimental. The HSR native signature contract reconstructs both 4.6.0
  profiles; future builds require runtime verification.

- Endfield 1.6.3 has an experimental Input System profile with keyboard-selection
  and capability patches. Legacy-only builds failed physical gameplay tests;
  the revised combined backend, inlined initialization fix and direct camera
  forwarding have validated WASD, capture, mouse look and menu clicks.

See [ZZZ analysis](docs/games/zzz.md), [HSR analysis](docs/games/hsr.md) and
[Endfield analysis](docs/games/endfield.md) for
build-specific details and remaining limitations.
