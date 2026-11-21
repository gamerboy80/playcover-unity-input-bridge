# Native desktop input for PlayCover

This project enables built-in desktop input paths in selected mobile Unity game
builds running under PlayCover. A native bridge forwards macOS keyboard, mouse
and trackpad events to Unity. Exact-build profiles describe the game patches,
binary identity and native input ABI.

The project is experimental. Reviewed profiles cover the builds below. ZZZ and HSR also
have automatic mapping detection for compatible updates. Game files are not
included or distributed.

## Supported builds

| Game | Profile | Backend | Status |
| --- | --- | --- | --- |
| Zenless Zone Zero 3.3.1 | [`zzz`](profiles/com.HoYoverse.Nap-3.3.1.json) | Unity Input System | Updated methods and object layouts verified; launch and device initialization checked |
| Zenless Zone Zero 3.3.1 | [`zzz-test`](profiles/com.HoYoverse.Nap-3.3.1-platform-pc-settings-test.json) | Unity Input System | Experimental app-platform and mobile-settings profile |
| Honkai: Star Rail 4.7.0 | [`hsr`](profiles/com.HoYoverse.hkrpgoversea-4.7.0.json) | Unity legacy input / InControl | Static verification complete, gameplay verification pending |
| Honkai: Star Rail 4.7.0 | [`hsr-test`](profiles/com.HoYoverse.hkrpgoversea-4.7.0-platform-pc-settings-test.json) | Unity legacy input / InControl | Experimental app-platform and mobile-settings profile |
| Arknights: Endfield 1.6.3 | [`com.gryphline.endfield.ios-1.6.3`](profiles/com.gryphline.endfield.ios-1.6.3.json) | Unity Input System + legacy input | Experimental; WASD, capture, mouse look and menu clicks validated |

Test-only profiles require explicit selection and are excluded from automatic
app matching. Validation applies only to the listed binary versions. See
[ZZZ analysis](docs/games/zzz.md) and [HSR analysis](docs/games/hsr.md) for details and
remaining limitations.

The ZZZ 3.3.0 and HSR 4.6.0 profiles remain available by their full IDs for older
installations and restoration.

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

The app's bundle ID, version, executable and original framework must match the
selected profile. Test profiles require explicit selection with `--profile`.

For a ZZZ or HSR update without a reviewed profile, `apply --profile zzz` or
`apply --profile hsr` tries to find the required methods and input mappings
automatically. ZZZ and HSR combine managed method lookup with native signatures.
HSR also verifies the targets of calls before editing cursor and menu behavior. An ambiguous
or missing match stops installation. Successful detection saves an exact-build
profile under `.local/profiles/`, so status, update and restore keep working.
Detection verifies the supported input ABI; gameplay on a new build still needs
checking.

To check detection and save its report without changing game files:

~~~sh
python3 patch.py resolve --app '/path/to/Zenless Zone Zero.app'
python3 patch.py resolve --profile zzz-test --app '/path/to/Zenless Zone Zero.app'
python3 patch.py resolve --profile hsr --app '/path/to/Honkai Star Rail.app'
~~~

Automatic detection covers the examined ZZZ metadata layout and HSR native
signature contract. A changed metadata format, native code shape or input backend
can require a resolver update. See
[signature detection](docs/signatures.md) for the checks and limitations.

The standard PlayCover app locations are under
`~/Library/Containers/io.playcover.PlayCover/Applications/`. Short profile names
are `zzz`, `hsr`, `zzz-test`, `hsr-test` and `endfield`. Endfield currently requires
explicit selection with `--profile endfield`; see its [porting notes](docs/games/endfield.md).

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
test profiles. Applying a different profile asks for confirmation, then restores
the active profile and applies the requested one. Press Enter or answer `n` to
cancel. Modified or incomplete installs must be repaired before switching.
A verified backup can be reused when applying that profile again.

Add `--verbose` to see profile IDs and file locations, or `--json` to print
status details as JSON. Incomplete or modified installs report that they need
attention instead of claiming to be unpatched. Run `python3 patch.py --help` for
the command options and examples.

The installer stores a compressed reverse diff for the original Unity framework,
plus full copies of the executable and signature resources, under
`.local/<profile-id>/`. The diff saves changed 64 KiB blocks, including bytes
changed by signing, and verifies the reconstructed original SHA-256 before use.
Existing full framework backups remain readable and are converted when applying
or updating a patch. Preserve this directory and the installed game for restoration.
Update applies the same profile to the same exact binary; it does not port patches to a newer
game release. Restore before updating the game. The installer rejects files that
changed after installation rather than overwriting them.

The desktop-input patch and the separate ZZMI Metal bridge can be installed in
either order. Each installer manages only its own load command and bridge file.
Restoring this patch removes `NativeInputBridge.dylib` and restores its Unity
framework edits while preserving `ZZMIMetal.dylib` if it is installed. Use
`zzmi uninstall` to remove the model bridge independently. Both tools keep their
shared ownership record in `.PlayCoverPatchRegistry` beside the app bundle.

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

Tests cover profile validation, binary edits, installer recovery, backup integrity,
and the shared event handler's key releases, capture controls and queued scroll
delivery using fake host/backend callbacks. AppKit wheel conversion is also
checked. Window and view checks require WindowServer
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

## PlayCover plugins

PlayCover builds with **Custom Plugins** support can load native dylibs through
PlayTools. The [Veritas Live preview](plugins/veritas/README.md) charts live Honkai: Star Rail damage from combat events.
The [ZZZ live damage preview](plugins/zzz_damage/README.md) shows damage and DPS
by source entity and includes a diagnostic capture for attribution checks.
