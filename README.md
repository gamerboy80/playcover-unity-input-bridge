# Native desktop input for PlayCover

This project enables built-in desktop input paths in selected mobile Unity game
builds running under PlayCover. A native bridge forwards macOS keyboard, mouse
and trackpad events to Unity. Exact-build profiles describe the game patches,
binary identity and native input ABI.

The project is experimental and supports only the listed game versions. It does
not provide or distribute game files.

## Supported builds

| Game | Profile | Backend | Status |
| --- | --- | --- | --- |
| Zenless Zone Zero 3.3.0 | [`com.HoYoverse.Nap-3.3.0`](profiles/com.HoYoverse.Nap-3.3.0.json) | Unity Input System | Keyboard, mouse capture/look and physical trackpad scrolling validated |
| Zenless Zone Zero 3.3.0 | [`com.HoYoverse.Nap-3.3.0-platform-pc-settings-test`](profiles/com.HoYoverse.Nap-3.3.0-platform-pc-settings-test.json) | Unity Input System | Test-only app-platform and settings profile |
| Honkai: Star Rail 4.6.0 | [`com.HoYoverse.hkrpgoversea-4.6.0`](profiles/com.HoYoverse.hkrpgoversea-4.6.0.json) | Unity legacy input / InControl | Keyboard, mouse capture/look, camera zoom and menu scrolling validated |
| Honkai: Star Rail 4.6.0 | [`com.HoYoverse.hkrpgoversea-4.6.0-platform-pc-settings-test`](profiles/com.HoYoverse.hkrpgoversea-4.6.0-platform-pc-settings-test.json) | Unity legacy input / InControl | Test-only PC-platform and mobile-settings profile |

Test-only profiles require explicit selection and are excluded from automatic
app matching. Validation applies only to the listed binary versions. See
[ZZZ analysis](docs/games/zzz.md) and [HSR analysis](docs/games/hsr.md) for details and
remaining limitations.

## Requirements

- Apple Silicon Mac running macOS
- Python 3.9 or newer
- Apple Command Line Tools, macOS SDK and Catalyst UIKit headers
- PlayCover with the matching decrypted game build installed

Full Xcode is not required. Keep a copy of the original app available for
restoration.

## Apply a profile

Close the game before applying, updating or restoring a profile. List the
profiles and copy-ready apply commands:

~~~sh
python3 patch.py profiles
~~~

For example, apply the regular HSR profile or its experimental test profile:

~~~sh
python3 patch.py apply --profile hsr
python3 patch.py apply --profile hsr-test
~~~

`apply` builds the bridge and installs it. To only build without installing,
run `python3 patch.py build --profile hsr`. `install` is also accepted as an
alias for `apply`.

For a game stored outside PlayCover's standard location, pass the app path:

~~~sh
python3 patch.py apply --profile hsr --app '/path/to/Honkai: Star Rail.app'
~~~

The app's bundle ID, version and executable must match the selected profile.
Unknown versions and mismatches are rejected. Test profiles must be selected
explicitly with `--profile`.

The standard PlayCover app locations are under
`~/Library/Containers/io.playcover.PlayCover/Applications/`. Short profile names
are `zzz`, `hsr`, `zzz-test` and `hsr-test`.

## Inspect, update and restore

Use `--app` to check or operate on whichever profile is currently applied:

~~~sh
python3 patch.py status --app '/path/to/Honkai: Star Rail.app'
python3 patch.py update --app '/path/to/Honkai: Star Rail.app'
python3 patch.py restore --app '/path/to/Honkai: Star Rail.app'
~~~

`status` reports `Patched (profile name)` when a saved profile matches the
installed files, and `Unpatched` when the original game files are present. With
`--app`, `status`, `update` and `restore` detect the active profile, including
test profiles. To switch profiles, restore the active one first, then apply the
new profile. A verified backup can be reused when applying that profile again.

Add `--verbose` to see profile IDs and file locations, or `--json` to print
status details as JSON. Incomplete or modified installs report that they need
attention instead of claiming to be unpatched. Run `python3 patch.py --help` for
the command options and examples.

The installer stores original binaries and signature resources under
`.local/<profile-id>/`. Preserve this directory for restoration. Update applies
the same profile to the same exact binary; it does not port patches to a newer
game release. Restore before updating the game. The installer rejects files that
changed after installation rather than overwriting them.

Only one install, update or restore operation should run at a time. Builds are
stored under `build/<profile-id>/`.

If an operation is interrupted, close the game and run `restore --app` with
the same app path. Restore can resume when the files match recorded originals
or planned patch files. It stops if it finds an unrecognized file, preserving
independent changes. Keep `.local/` even when an operation fails.

## Input behavior

Disable PlayCover keymapping while using the bridge. The game can capture the
mouse natively; Option+M is an optional fallback capture toggle and Escape
releases manual capture. Losing app focus releases held keys and mouse capture.
Native text fields and other app windows retain their normal keyboard input.

Trackpad and Magic Mouse movement is accumulated until 16 points produce one
standard 120-unit wheel step. Physical notched wheels remain immediate. See the
analysis notes for implementation details and hardware validation.

PlayTools window and display adjustments can remain enabled with keymapping off.
The optional source change in
[patches/playtools-native-pointer-lock.patch](patches/playtools-native-pointer-lock.patch)
is separate from game profiles and is not installed automatically.

## Development

Run the synthetic/native checks and build a profile:

~~~sh
sh tests/run.sh
python3 patch.py build --profile com.HoYoverse.Nap-3.3.0
~~~

Tests cover profile validation, binary edits, installer rollback, input-state
handling and AppKit wheel conversion. Window and view checks require WindowServer
access and are skipped in headless environments. Synthetic checks do not
validate live game behavior.

See [porting instructions](docs/porting.md) before adding a profile or backend.
[AGENTS.md](AGENTS.md) records repository invariants for contributors and
automation.

## Distribution and diagnostics

Game binaries, metadata dumps, installation backups and runtime logs are local
artifacts and must not be committed. Diagnostic logs contain aggregate bridge
state and scroll counters; they do not record key identities or pointer
coordinates. Logs are stored in the app container under
`Data/Documents/LogDir/NativeInputBridge.log`.

Original project code and documentation are licensed under the [MIT License](LICENSE).
That license does not grant rights to game code or assets. The optional
PlayTools patch remains under its upstream AGPL-3.0 license in
[patches/PlayTools-LICENSE](patches/PlayTools-LICENSE).
