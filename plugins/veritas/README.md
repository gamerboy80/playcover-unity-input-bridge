# Veritas for PlayCover

A native ARM64 Catalyst port of the local Veritas 0.2.58 source, for the reviewed
international **HSR 4.7.0** build (`com.HoYoverse.hkrpgoversea`). It observes combat
without changing damage, stats, turn order or the game account.

The overlay provides:

- Character DMG/DPAV meters with gray overkill segments and automatic portraits.
- Character legend, damage distribution and stacked damage/overkill bars.
- Damage-category pie/bar charts, team or character scope, tables and legends.
- Live turn/AV graphs, battle metrics, wave/cycle tracking and relative AV resets.
- Enemy portraits/HP, lineup/formation tracking, live character stats and history.
- Localized manual skill names, categories, config IDs and accumulated damage.
- Upstream-compatible JSON and comprehensive CSV exports; optional automatic
  saving and date folders. Previous results can be selected from the history menu.
- A local Socket.IO v4 event API and an in-overlay console.
- Saved panel layout, light/dark palettes, custom accent/text size, opacity,
  the upstream translation catalog, auto-hide and a custom streamer banner.

Gross damage and overkill remain separate. Like upstream, skill totals group
subsequent damage under that owner's most recent manual skill, including delayed
effects. This grouping does not establish which skill caused a delayed hit.
Unattributed direct HP loss is retained separately.

## Controls

**⌘⇧D** toggles visibility. **⌘⇧E** enters or exits layout editing.
Click a visible panel's gear or chart tabs directly. The gear menu lists both
shortcuts and exposes all widgets, chart options, appearance,
exports, history, help and release information. Closing editing returns pointer
and keyboard focus to the game. During editing, scroll panel contents, drag a
panel's title to move it, or drag its lower-right handle to resize it. The main panel remains accessible in editing
mode even if every widget was hidden.

Streamer mode covers the usual UID area and replaces character labels with
aliases. Panel visibility and settings survive restarts. Charts retain the last
result unless automatic hiding is enabled.

## Build and prepare a copy

Requires Apple Silicon, Xcode Command Line Tools, Python 3.9+, and PlayTools
with Custom Plugins support. Quit HSR before staging. From the repository root:

```sh
sh plugins/veritas/build.sh
python3 plugins/veritas/stage.py \
  --app "$HOME/Library/Containers/io.playcover.PlayCover/Applications/com.HoYoverse.hkrpgoversea.app" \
  --output build/plugins/HSR-Veritas-Preview.app
```

The command clones the app, resolves and verifies its bindings, adds the native
plugin to `Frameworks/UserPlugins`, then signs and verifies the copy. The source
app, desktop-input installation, other plugins and backups are preserved. The
copy uses the same PlayCover data/account container. Remove any obsolete
**VeritasReports** Custom Plugins entry before using the new preview.

To prepare hooks for a different plugin loader, add `--without-plugin`, then
load `build/plugins/VeritasLive.dylib` into that copy with your existing loader.
The standalone dylib refuses an ordinary app or an older six-hook preview.
Do not unload it while the game is running.

## Name-based lookup

All managed HSR functions are found through the game's method metadata by
class/method name, with native instruction validation selecting overloads.
Three internal IL2CPP helpers use independent native signatures. Runtime enum
reflection supplies property and attack-category names; field reflection reads
ExtraTeam, SkillConfigID and icon paths. This avoids copying Windows enum values
or guessing additional field offsets.

Like the main desktop-input patch, function discovery happens while preparing
the build. It does **not** resolve every invocation at runtime. The reviewed
profile still records the expected ABI, original hashes, detour bytes, object
fields and available cave storage. Unknown builds, ambiguous names/signatures
and changed code stop staging. New versions require an ABI review.

Check lookup without changing the app:

```sh
python3 plugins/veritas/stage.py --resolve --app '/path/to/Honkai Star Rail.app'
python3 plugins/zzz_damage/stage.py --resolve --app '/path/to/Zenless Zone Zero.app'
```

Reports are saved under `.local/profiles/plugins/`. A verified desktop-input
installation can be resolved using its installer state and hash-checked original,
without adding its current signing hash to a permanent allowlist.

## Exports and API

Exports default to the game's container at `Documents/Veritas/Exports/`.
The Export menu supports a custom folder, date subfolders, JSON/CSV sharing, and
automatic saving after battle. JSON uses upstream's camel-case fields and adds
`_playcover` with the native capture; CSV includes character summaries and skill
details. Stat history keeps each property's final value per turn. The optional
raw event journal retains up to 200,000 events and reports overflow explicitly.

The event server listens on **127.0.0.1:1305**, using Socket.IO/Engine.IO v4
polling, direct WebSocket connections and polling-to-WebSocket upgrades. Standard
clients can use their default transport settings. It emits `Connected`, battle/lineup/turn, damage, skill,
wave/cycle, stats, formation and enemy-initialization packets. No battle data
is uploaded by this plugin. External analysis clients are a separate choice.
The release-information action contacts GitHub only when selected; upstream's
Windows self-updater is replaced with native rebuild instructions.

Portraits are loaded from the game and converted through temporary Unity render
textures. Conversion failure uses a text/initials fallback. Optional local PNGs
can be placed at `Documents/Veritas/Portraits/avatars/<avatar-id>.png` or
`.../enemies/<monster-template-id>.png` before launch. Game assets are not bundled
in this repository.

## Validation

```sh
sh tests/run.sh
sh plugins/veritas/build.sh
sh plugins/zzz_damage/build.sh
sh plugins/veritas/preview.sh
```

The last command renders `build/plugins/VeritasPreview.png` using synthetic data
and the actual UI components. Native tests exercise aggregation, exports,
Socket.IO polling/WebSocket handshakes and upgrades, runtime-name decoding and render-target cleanup after errors.
Optional real-game lookup checks use `PLUGIN_GAME_FIXTURES=1` with the Python tests.
These checks do not validate gameplay. The expanded combat hooks, portraits,
reflection, support units, wave/AV transitions and menus still need a live
operator-controlled battle. See [native evidence and platform differences](../../docs/games/veritas.md).

Adapted upstream code, colors and translations retain their
[MIT notice](UPSTREAM-LICENSE).
