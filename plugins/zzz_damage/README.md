# ZZZ damage-event probe

An explicitly selected live damage meter and diagnostic for international ZZZ **3.3.1 build 4** under
PlayCover. It captures the damage-text input event before that handler's display
filters and formatting. It records the candidate amount, source/target runtime
entity IDs, and matching entity lookups made by the original game code. It does
not assign damage to the active agent or guess agent names from entity IDs.

The preview shows raw damage-display totals, their average rate, the latest
source, and share by agent or source. The gear menu lists the meter shortcuts
and all five training markers. Use **Control+Command+D** to show or hide it and
**Control+Command+R** to reset manually. The meter also resets when the game's
battle-statistics session begins. This hook still needs a live check across
battle modes. Use the manual reset for training comparisons.
The session-exit hook freezes the totals, source shares and DPS at battle end.
Result-screen entry also freezes game seconds and DPS. Manual reset clears the
result and resumes counting. The battle-start hook also resets and resumes.
DPS refreshes on hits and every 100 ms, using scaled game time from the first
counted hit through the current tick, including
gaps between hits. The clock accumulates the time-slow manager's scaled frame
delta. The panel keeps the final values until reset. Chain-attack and ultimate
timing still need comparison against the live game clock.

The meter groups resolved agents by roster ID across changes to their runtime
source IDs. It reads the character-name key from the game's role configuration
and translates it
using the game's text service. It caches labels until the meter is reset.
If a name is unavailable, the overlay shows the roster ID. Unresolved
sources use the Unity object name and runtime ID when available. Captures
include `source_avatar_id`, with 0 for an unresolved source.
Icon paths and untranslated keys fall back to the roster ID.
The meter counts positive, visible
events with matching source and target lookups and the entity kinds observed
for agent-to-enemy hits in training. It shows the five largest sources and
groups the rest under Other. Summon ownership, anomaly/disorder attribution,
full event coverage and effective HP loss still need verification. See the
[native analysis](../../docs/games/zzz-damage-probe.md).

## Name-based lookup

Staging resolves the eight hook targets and identified helpers by managed
class/method name through the same metadata resolver as the main patch, then
checks their native instructions. Remaining obfuscated helpers use unique native
signatures. The resolved map must match this build's reviewed object/ABI profile;
missing or ambiguous matches stop staging. Object fields and cave reservations
remain build-specific JSON data.

To inspect discovery without changing the app, run
`python3 plugins/zzz_damage/stage.py --resolve --app '/path/to/Zenless Zone Zero.app'`.
The report is saved under `.local/profiles/plugins/`. This is preparation-time
lookup, not per-call runtime reflection or automatic approval of a new build.

## Build and stage

Quit ZZZ. From the repository root:

```sh
sh plugins/zzz_damage/build.sh
python3 plugins/zzz_damage/stage.py \
  --app "$HOME/Library/Containers/io.playcover.PlayCover/Applications/com.HoYoverse.Nap.app" \
  --output build/plugins/ZZZ-Damage-Probe.app
```

The stager accepts the reviewed original framework, the recorded examined test
install, or a desktop-input installation whose active state, installed hashes and
reconstructed original pass the main installer's checks. It checks the metadata hash, framework hash, UUID,
entry instructions, nonoverlapping edits and unused segment padding. It records
source/planned hashes before editing the isolated copy, includes the plugin in
`Frameworks/UserPlugins`, and signs/verifies the copy. Existing input patches,
load commands and other plugins are retained. The source installation and its
backup state are untouched. The preview uses the same game account/data container.

After successfully staging a new preview in `build/plugins`, the stager removes
older `ZZZ-Damage-*.app` previews whose recorded framework, executable and plugin
hashes still match. Modified or unrecognized copies are kept.

Open the staged copy with a PlayTools build that loads Custom Plugins. Loading
the standalone dylib into the ordinary app is insufficient: it requires the
staged framework hooks. Remove/quit the preview to stop using the probe. Quit
before rebuilding or replacing a preview; do not unload the dylib in a running game.

## Controlled training check

Keep damage numbers enabled. Disable Bangboo/other damage sources where training
allows it. Pick agent A with a persistent direct attack that can continue after
switching to agent B. The labels below are your experimental expectations; the
plugin does not treat them as confirmed ownership.

1. In training, press **⌃⌘1**. Use only A and record at least three isolated hits.
   Write down a few unmerged damage numbers for amount comparison.
2. Switch to B, let A's effects finish, then press **⌃⌘2**. Record at least three
   isolated B hits with no assist, companion or anomaly damage mixed in.
3. Press **⌃⌘0**, switch back to A, and start its persistent attack. Switch to B,
   then press **⌃⌘3** only once B is on field. Stop attacking and capture the
   remaining A hits. Repeat this step with **⌃⌘0** before each setup if needed
   to collect three post-swap hits. A switch attack from B makes this phase
   ambiguous; repeat in a new capture if necessary.
4. **⌃⌘4** labels other-source experiments (Bangboo, anomaly/disorder, summons).
   **⌃⌘0** returns to unlabelled capture. These events do not establish the A/B mapping.

Markers use **Control+Command+digit** on the main number row. Command allows
them through the desktop-input bridge. Earlier Command+Shift shortcuts
conflicted with macOS screenshots; Control+Option shortcuts were consumed by
the input bridge. Regression checks exercise all five markers through the shared
event handler before decoding them in the plugin.
The probe logs `Ready`/`Hooks unavailable` and phase changes to the macOS console.
It creates a private, unique JSONL file under the game's container:

```text
Data/Documents/LogDir/ZZZDamageProbe-<session>.jsonl
```

Diagnostic capture is bounded to 4,096 candidate events and 64 phase markers per
launch. The live meter continues after the diagnostic cap.
There is no upload, raw pointer dump, account ID or input recording. Captured
runtime IDs are entity IDs, not account UIDs. Keep captures local and untracked.

Summarize one capture, optionally checking individual hit sequences against the
numbers you observed (the numbers here are syntax examples):

```sh
python3 plugins/zzz_damage/report.py '/path/to/ZZZDamageProbe-session.jsonl'
python3 plugins/zzz_damage/report.py '/path/to/ZZZDamageProbe-session.jsonl' \
  --expect-hit 12=1235 --expect-hit 15=947
```

`attribution_check: consistent` requires three positive events in each marked
phase, matching source and target lookups, distinct A/B source IDs, and the same
A source ID after swapping. Missing lookups, mixed sources, short/truncated
captures and missing markers produce `inconclusive`. Individual amount checks
allow display rounding; they do not establish HP damage or complete coverage.
Unexpected or inconclusive results are evidence for further tracing, not a reason
to substitute the active agent as the damage source.

## Validation

Synthetic tests cover event decoding, lookup identity checks, detour byte
preservation and controlled-source report failures. These do not validate live
game damage. Record physical training outcomes separately in the analysis notes.
