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

## Build and install

Close the game before installing, updating or restoring a profile. List available
profiles:

~~~sh
python3 patch.py profiles
~~~

Build and install the stable ZZZ profile:

~~~sh
python3 patch.py build --profile com.HoYoverse.Nap-3.3.0
python3 patch.py install --profile com.HoYoverse.Nap-3.3.0
~~~

For another app location, pass its bundle path:

~~~sh
python3 patch.py install --profile com.HoYoverse.Nap-3.3.0 --app '/path/to/Zenless Zone Zero.app'
~~~

When an app path is provided, its bundle ID, version and executable are matched
to an exact profile. Unknown versions and mismatches are rejected. The framework
SHA-256 and every expected patch byte must also match before installation.
Test-only profiles must be selected explicitly with `--profile`.

The default ZZZ app path is
`~/Library/Containers/io.playcover.PlayCover/Applications/com.HoYoverse.Nap.app`.
The HSR profile can be selected by its canonical ID or the `hsr` alias.

## Inspect, update and restore

~~~sh
python3 patch.py status --profile com.HoYoverse.Nap-3.3.0
python3 patch.py update --profile com.HoYoverse.Nap-3.3.0
python3 patch.py restore --profile com.HoYoverse.Nap-3.3.0
~~~

The installer stores original binaries and signature resources under
`.local/<profile-id>/`. Preserve this directory for restoration. Update applies
the same profile to the same exact binary; it does not port patches to a newer
game release. Restore before updating the game. The installer rejects files that
changed after installation rather than overwriting them.

Only one install, update or restore operation should run at a time. Builds are
stored under `build/<profile-id>/`.

## Input behavior

Disable PlayCover keymapping while using the bridge. The game can capture the
mouse natively; Option+M is an optional fallback capture toggle and Escape
releases manual capture. Losing app focus releases held keys and mouse capture.

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
