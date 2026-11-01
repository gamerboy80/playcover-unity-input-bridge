# Porting to another build or game

The reusable part is macOS event handling and a specific Unity Input System ABI.
The profile supplies game identity, binary edits, addresses and field offsets.
A similar Unity or HoYoverse game is not automatically compatible. This repository
contains the ZZZ new Input System profile and an experimental HSR legacy/InControl
profile. Both use one AppKit host; `bridge.backend` selects game-facing code.
See [HSR's backend contract](hsr.md) for `unity-legacy-v1`. The tables below
describe the ZZZ `unity-input-system-v1` contract.

## Select and build a profile

```sh
python3 patch.py profiles
python3 patch.py build --profile zzz-3.3.0
python3 patch.py install --profile zzz-3.3.0 --app '/path/to/Game.app'
python3 patch.py status --profile zzz-3.3.0 --app '/path/to/Game.app'
python3 patch.py update --profile zzz-3.3.0 --app '/path/to/Game.app'
python3 patch.py restore --profile zzz-3.3.0 --app '/path/to/Game.app'
```

`zzz-3.3.0` remains the default for existing commands. Without `--app`, the bundle
ID selects PlayCover's application path. `update` rebuilds/reapplies the **same
exact game build's** patch; it does not port a patch to a game update.

Output is isolated in `build/<profile-id>/`. New installation backups and state
live in `.local/<profile-id>/`; each profile supports one app installation at a
time. The pre-profile `.local/state.json` and `.local/original/` remain usable for
the matching original framework hash. The installer does not move or overwrite
those backups. Restore before updating the game; an externally updated game will
fail the installed-hash guard and must not be overwritten with an old backup.

## Profile format

Copy the existing JSON to a **new** filename/ID such as `game-1.2.3-build2.json`.
Do not create a purported supported profile with guessed addresses. Keep old
profiles for restoration and reproducibility. `profiles.py` validates the data;
no third-party Python packages are required.

| Field | Meaning |
| --- | --- |
| `schema_version` | Currently `1`; incompatible format changes need a new version. |
| `id` | Lowercase letters, digits, dots and hyphens; equals the filename stem. |
| `game`, `version`, `bundle_id`, `executable` | Display name and exact Info.plist identity (`CFBundleShortVersionString`, `CFBundleIdentifier`, `CFBundleExecutable`). |
| `architecture` | Currently only thin arm64 Catalyst is supported. |
| `framework_binary` | Bundle-relative `Frameworks/<name>.framework/<name>`. |
| `original_sha256` | Full original decrypted framework hash, before patches/signing. |
| `patches` | List of named fixed-length edits to that framework. An empty list is allowed if no byte edits are needed. |
| `bridge` | The selected ABI, image suffix, expected payload size, addresses and fields described below. |
| `validation` | Physical keyboard/mouse and trackpad results, plus analysis-note location. Record failures and untested behavior explicitly. |

Each byte edit has `name`, `reason`, `file_offset`, `expected`, and `replacement`.
Offsets are hexadecimal strings; bytes are hexadecimal pairs without spaces.
The loader rejects unequal lengths, overlaps and unaligned arm64 edits. The
installer first verifies the whole original hash, then every expected byte range.
Only the explicit replacement ranges may change before signing.

For the existing ZZZ profile the one edit is:

```json
{
  "name": "pc-input-selector",
  "reason": "Return the independently verified PC enum 2",
  "file_offset": "0xc22d6b8",
  "expected": "f44fbea9fd7b01a9",
  "replacement": "40008052c0035fd6"
}
```

This entry is a build-specific example, not a signature to scan for in other games.
Other functions can start with exactly the same prologue.

## Shared backend contract

`bridge.backend = "unity-input-system-v1"` names this repository's verified ABI
contract; it is not a claim that every Input System 1.x release is interchangeable.
`image_suffix` must match the selected framework path. All `addresses` are
preferred Mach-O VM addresses; ASLR is applied at runtime using the image's slide.
They are not file offsets or offsets from the runtime image header.

The generated `Profile.h` exposes each address as `Game<Name>` and each field as
`GameField<Name>`. Never edit that generated file. Its constants are compiled
into the bridge for exactly one profile. The bridge checks bundle ID/version
before initialization; the installer's framework hash check is the stronger
binary-identity guard. Do not copy the dylib manually to an unverified build.

| `addresses` name | Existing bridge call contract / purpose |
| --- | --- |
| `Statics` | Address of a pointer to this build's managed static-storage region. |
| `NewString` | `void *(const char *, int)`; UTF-8 with explicit byte length. |
| `AddDevice` | `uintptr_t(void *, void *, void *)`; layout/name/variants strings. |
| `MouseMakeCurrent` | `void(uintptr_t)`; make the bridge Mouse current. |
| `NativeTime` | `double(void)`; input event clock. |
| `QueueInputEvent` | `void(void *)`; pointer to the packed StateEvent. |
| `ScreenWidth`, `ScreenHeight` | `int(void)`; Unity pixel dimensions. |
| `CursorLock`, `CursorVisible` | `int(void)` / `BOOL(void)`; capture state. |
| `ReadVector2` | Two-float struct return `(uintptr_t control, void *methodInfo)`; health check only. |
| `EnableMouseProcessing` | `void(BOOL)`; ZZZ-specific initialization after Mouse creation. Use `"0x0"` only when verified unnecessary for a port. |

Optional addresses default to `0x0` (disabled). `LegacyMousePresentSlot` is the
preferred VM address of the **writable native callback pointer** behind legacy
`Input.mousePresent`; it must be pointer-aligned. The bridge replaces that pointer
once after device validation, returns true while ready, and calls the saved
original callback otherwise. It does not patch the method's executable bytes.
`LegacyMousePresent` is the `BOOL(void)` getter used for diagnostic verification.
Recover and verify both on each port; the examined iOS player returned false
while the bridge Mouse existed, causing the UI to skip mouse processing.

The optional `GetMouseProcessing` (`uintptr_t(void)`), `MouseProcessingEnabled`
(`BOOL(uintptr_t)`), and `ReadProcessedScroll` (two-float struct return
`(uintptr_t)`) inspect the game's mouse processor for bounded diagnostics only.
These names are accepted by `profiles.py`; unsupported profiles need not include them.

These are the casts used by the existing code. Verify native calling conventions,
hidden MethodInfo parameters, static versus instance methods, and arm64 struct
return rules against the new binary; a matching managed method name is insufficient.
If a game's method does not fit a contract, implement the required backend change
explicitly rather than putting an incompatible address in this table.

| `fields` name | Offset relative to |
| --- | --- |
| `StaticInputManager`, `StaticKeyboard`, `StaticMouse` | The dereferenced `Statics` region. |
| `DeviceID` | InputDevice object; signed 32-bit ID. |
| `StateBlock` | InputControl object; four uint32 words: format, byte offset, bit offset, size in bits. |
| `MousePosition`, `MouseDelta`, `MouseScroll` | Mouse object; control pointers. |

The shared backend assumes a 24-byte StateEvent header (20-byte base event plus
four-byte format), `MOUS` state beginning with the standard packed 30-byte
position/delta/scroll/buttons prefix, and `KEYS` with a 14-byte Unity Key bitset.
The key enum/table and modifier mapping are part of this backend. Verify these
on a new game too. `mouse_state_bytes` is the exact live payload size (49 in the
examined ZZZ build); extension bytes are zero-filled, up to a 64-byte bound. The
bridge rejects a different live size/format. Larger or different payload layouts,
different static storage, or an engine without this Input System require code.

## Analysis and validation workflow

1. Start from an unmodified decrypted app. Record its bundle identity, executable,
   architecture, framework SHA-256 and Mach-O segment mapping. Keep originals local.
2. Locate the PC input selector and establish its enum/behavior independently.
   Record expected instructions and fixed-length replacement. Use bounded
   disassembly; matching an obfuscated name or prologue is not sufficient evidence.
3. Recover every backend method and field in the table. Use metadata, cross
   references, method signatures and native disassembly together. Pay attention to
   VM/file mapping: this ZZZ framework's late data differs by `0x10000`.
4. Determine device layouts and initialization timing. Check null Mouse controls
   before enabling game-specific mouse processing. Document any game-specific hook.
5. Add the JSON and analysis notes; run the tests and build. Inspect the generated
   header against your notes. Synthetic tests validate config, conversion and
   rollback; they cannot prove native method addresses are correct.
6. On an explicitly selected closed app, install with its exact profile. Verify
   signatures, configuration loading and device setup before entering gameplay.
   Check physical keyboard releases, modifiers, F-keys, mouse buttons/look, native
   capture and focus loss with PlayCover keymapping off. Preserve unrelated PlayTools
   display/window fixes and its native pointer-lock source patch when applicable.
7. Test physical wheels and precise trackpads separately, in menus and gameplay.
   Record successes and failures in `validation` and analysis notes. The present
   ZZZ trackpad implementation was confirmed working only after bridging the
   legacy mouse-presence callback; native event tests and nonzero scroll state
   alone had been insufficient. Do not inherit a success claim for a new port.
8. Exercise restore and retain the original backup. Commit authored profiles,
   source and notes only; never game binaries, metadata dumps or account logs.
