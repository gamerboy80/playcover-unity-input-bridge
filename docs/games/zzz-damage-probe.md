# ZZZ 3.3.1 damage-event probe

This research profile is separate from desktop-input profiles and the HSR
Veritas backend. The original international 3.3.1 build 4 framework SHA-256 is
`657b2def5d3f7f687965bcc2764252ee579dc2701cf0a999ebea7da824c24d94`.
`plugins/zzz_damage/zzz-3.3.1.json` also records the exact examined installed
desktop-input test framework, metadata hash and image UUID. Other signed
variants are not accepted merely because they share a version or UUID.

## Method and ABI evidence

Addresses below are preferred Mach-O VM addresses. This image's preferred TEXT
base is zero; runtime code adds the loaded image header. File access still uses
the segment mapping, and static/object offsets are distinct.

Named IL2CPP methods were resolved against the original framework using the
existing `signatures.Metadata` and `resolve_functions`, with the independently
reviewed Logic.dll `MouseInputEnhancement.get_CurrentScrollDelta` registration
anchor. Metadata return-type references independently associate both entity
lookup paths with `MoleMole.Battle.Entity`.

| Method | Preferred VM | Evidence/use |
| --- | --- | --- |
| `MoleMole.UIInLevelDamageTextContainerChildWindowController.GMBBKAAGOJA` | `0xba86700` | One managed parameter; x0 controller, x1 pointer to an unboxed/by-reference event payload. No FP arguments. Probe preserves x2 as hidden method context. |
| `GDIACAHPLBB.EIMKFKGAHBN` | `0xd2d901c` | Instance entity lookup: x0 manager, w1 runtime entity ID, x0 entity result. Probe forwards x2 method context and returns the original pointer. |
| `MoleMole.EntityHandle.Get` | `0xf018eac` | Compares cached runtime ID against entity `+0x38`; invalidates stale handles. Establishes entity runtime-ID field. |
| `MoleMole.EntityHandle.get_entityType` | `0xf018f38` | Calls `Get`, then loads w0 from entity `+0x50`. Establishes numeric entity-kind field; no enum meanings assumed. |

Bounded ARM64 inspection establishes the following accesses. Full proprietary
disassembly and metadata stay outside tracked source.

| Payload access | Native evidence | Probe meaning |
| --- | --- | --- |
| `+0x00` uint32 | `0xba8677c` loads w1 before entity lookup at `0xba86780` | Target/text-follow entity ID candidate |
| `+0x04` uint32 | `0xba86af0` loads w1 before lookup at `0xba86af4`, inside `HJOHFLHCPLI` | Source entity ID candidate |
| `+0x34` float | `0xba867a4` loads s0 and compares against zero; `0xba869d8` reloads this value for formatting | Numeric damage candidate before presentation changes |
| `+0x38` uint32 | `0xba86790` reads this selector; value 1 skips rendering | Raw kind/selector, not an established damage-type enum |
| `+0x3c` byte | `0xba8679c` tests bit 0 and skips rendering | Raw hidden/filter flag |
| `+0x57` byte | `0xba867b0` tests bit 0 and skips rendering | Raw suppression flag |

The event's native consumer reads through `+0x69`. The probe reads only the
listed scalar fields from that same valid incoming pointer. It snapshots them
before the original handler and logs after the original returns. The second
hook observes the game's own entity lookups within that handler; it makes no
additional entity queries, stores no game object pointers past the call, and
uses thread-local nesting to separate recursive events. Exceptions restore the
previous nesting frame before propagating.

`HJOHFLHCPLI` can randomize/transform the displayed value after reading `+0x34`.
`QueryDamageTextInfo` concerns presentation parameters; it is not the damage
source. `BattleStatsSubsystem.OnUpdate` forwards to base behavior and the
examined `UIAutoBattleStatItemWidgetController.RefreshStat` is a stub. None of
these establishes a ready-made combat feed.

## Detour evidence

The two entries each move exactly 12 reviewed, PC-independent prologue bytes
into a trampoline. The overwritten bytes and generated jump are equal length.
DamageEvent moves stack pair stores; LookupEntity moves two stack pair stores
and frame-pointer setup. Neither displaced region contains a PC-relative
instruction. Native calling conventions and return values are preserved.

Two 48-byte stub reservations start at preferred VM `0x18dc4030`, after the last
TEXT section ending at `0x18dc402d` and before the TEXT segment end `0x18dc8000`.
The original bytes are zero. Two eight-byte callback slots start at `0x1bd94500`,
after `__DATA,__common` and before DATA segment end `0x1bd98000`, beyond its
file-backed data. Section overlap, alignment, function boundaries, expected bytes
and exact source hash are checked before editing. No segment or load command is
added to the game framework.

Empty slots execute the original routine. The plugin verifies game identity,
UUID, both jumps and full stub bytes before publishing either callback. Entity
lookup is published before damage capture. Existing nonempty slots cause a
refusal, avoiding duplicate registration. Callbacks remain installed until game
exit; hot unloading is unsupported.

## Current validation and limits

Static mapping and original-byte/padding checks have been completed. The full
test runner passed (74 Python tests, three optional local-fixture skips, plus
native checks; the native window-binding check skipped without WindowServer).
The desktop-input bridge and probe dylib build with warnings as errors. The
signed staged app's complete detours and hashes were checked, and the installed
framework hash remained unchanged.

On 2026-11-20 the isolated copy launched and the live probe recorded both hooks
ready. A subsequent controlled training capture recorded 16 finite positive
events. All 16 resolved both source and target entities with matching runtime
IDs. The operator identified agent A as Alice and B as Nangong. The first four
events shared one source ID; the next five shared a different source ID; the
final seven returned to Alice's source ID. All targeted the same enemy entity.
This supports separate direct-hit source attribution for these two agents in
that session. Numeric amounts were captured, but have not yet been independently
compared with observed display numbers or effective HP loss.

The third phase marker was absent: the original Command+Shift+3 shortcut
conflicted with macOS screenshots. The later Alice events therefore remained
labelled phase 2. Their exact relationship to the swap has not been confirmed,
so the report correctly returned `inconclusive` for the full off-field check.
The next run captured 100 events, including 75 positive amounts and 25 zero
amounts. All 75 positive events resolved matching source and target entities.
The first four hits used one source, the next four another. During the later
attack sequence these sources interleaved without being merged into the most
recent attacker. The operator reported possibly attacking with Nangong during
Alice's continuing damage. This supports concurrent source separation, but is
not an unambiguous controlled confirmation of off-field ownership.

That run contained no markers. The desktop-input bridge consumes mapped keys
unless Command is held, so the intermediate Control+Option marker combination
never reached the plugin's local event monitor. Marker shortcuts now use
Control+Command+digits 0–4, read by physical number-row key code. Tests send all
five through the production shared event handler, then the plugin's decoder;
they also reproduce the consumed Control+Option path and reject the original
screenshot shortcuts. Agent labels are operator-supplied; runtime IDs are
session-local. The captures retain their original phase labels. The corrected
preview launched and reported both hooks ready.

The corrected preview recorded markers 1, 2 and 3 in live training. Phase 1
had five positive events from Alice's source. After the operator marked phase 3
with Nangong on field, the first 22 positive events carried that same Alice
source, with matching source and target lookups. Some recurred at roughly
one-second intervals. Their underlying effect and correspondence to displayed
damage or HP loss remain unverified.

A second phase 2 marker isolated the Nangong retest. All four positive events
after that marker resolved to Nangong's source, distinct from Alice's, and all
four target lookups matched. The session-wide report remains inconclusive
because it combines repeated phase labels and includes mixed-source gameplay
outside the isolated test windows.

The earlier discarded capture also included enemy-to-agent events. This is a
bidirectional event source, so a future player-damage meter must establish
player/target classification before aggregating combat totals. The probe
deliberately preserves these events for analysis.

The first controlled check compares A-only and B-only source IDs, then tests A's
continuing attack with B active. Names and agent config IDs are deliberately
unresolved. A source entity can be a summon. Shared anomaly contributions,
disorder, reflected damage, shields, overkill, healing, invulnerability and
environmental damage require separate experiments. This event is on a display
path; delivery with damage text disabled, controller lifecycle changes, grouped
events and other damage paths must be checked before totals or DPS are trusted.

See the [probe instructions](../../plugins/zzz_damage/README.md) for capture
markers and the report command. A synthetic `consistent` report is not a
hardware result. A live `consistent` report establishes only source consistency
under the operator's controlled sequence, not complete combat attribution.

## Live meter preview

The meter uses the same two hooks and binary profile. In training, the positive
outgoing events observed so far had source kind 1, target kind 2, and event
selector 0 or 2. The recorded enemy-to-agent events reversed the entity kinds.
The meter requires matching lookups and applies that observed outgoing filter,
then groups by source runtime ID. Other entity kinds and incomplete lookups
require further validation before inclusion.

Totals reset manually. The first-to-latest hit interval determines displayed
DPS. The overlay refreshes four times per second and the diagnostic log retains
its independent cap. The meter adds no binary edits beyond the probe hooks.

Automatic labels read the matched source entity's Unity root object on the
main thread. The Logic.dll `MoleMole.Battle.Entity.get_Root` at `0xb2001d0`
reads the GameObject at +0x40. CoreModule's `Object.GetCachedPtr` at
`0x12e9b2d4` verifies the live native object at +0x10 before calling
`Object.get_name` at `0x12e9b3b0`. The string length getter at `0x10be93a4`
reads +0x10, followed by UTF-16 characters at +0x14. The plugin copies the
name during the native lookup and retains no object pointer. It groups hits by
ID and copied name to distinguish reused IDs with different names. Unity
names can be internal and are independent of localized roster names.

## Upstream attribution research

Live labels such as `Avatar:220 (#220)` repeat the combat entity ID. The
overlay suppresses that redundant name. These IDs can change for the same
character and can be reused. Roster IDs are a separate namespace. The
[community ID list](https://github.com/donutman07/Zenless-Zone-Zero-ZZZ-Character-IDs/blob/main/ZZZCharacterIDs.md)
gives Alice as 1401 and Nangong Yu as 1511. The native roster getter
`InLevelAvatarDataItem.GetAvatarTemplateID` at `0xbf3d920` reads +0x68,
which its initializer at `0xbf3d5e0` writes from a uint32 argument.

`APNCODNOFLH.NDBEPJPKGEK` at `0xe428fd8` demonstrates a direct lookup
from an avatar combat entity to that roster record. Its helper at
`0xe4290e4` takes the entity in x0, checks entity kind +0x50 for 1, and
looks up component slot 29 via `0x7c4159c`. It checks the component type,
reads its +0x98 reference, and returns the reference only if it has the
avatar actor class. `HJGOAJHNEGC.HJJKLFDKFLO` at `0xb751924` then
type-checks the actor's +0x98 reference as `InLevelAvatarDataItem`. The
caller reads the record's +0x68 and compares it against 2011 and 2021
(Wise and Belle in the roster list).

The construction path corroborates those fields. `AvatarInitData.CreateByAvatarItemData`
at `0xefce958` reads the roster item +0x5c and passes it to the helper at
`0xefcead4`, which stores it at init data +0x40. `0xa793ddc` carries that
value into the `InLevelAvatarDataItem` constructor. `0xc2614bc` forwards
the resulting record to `DGABGEJCPGP.AGLKIDGNAHB` at `0xab812f8`.
That function forwards the same record to `HJGOAJHNEGC.EDEFLFIKNFK` at
`0xb752908`, where `0xb752a6c` stores the pointer at actor +0x98.

The probe uses these two byte-checked helpers on the resolved source
entity on the main thread. It logs the resulting template ID separately from
the runtime ID and uses it for meter aggregation. Synthetic checks cover
runtime ID reuse and changes. Controlled Alice and Nangong hits before,
during, and after switches are still needed to validate live results.
Owner resolution for non-avatar sources remains open.

Agent labels use `GKHEGNDIKMM.KNMOEANDPIE` at `0xf832908`.
`UINewbieGuideFetchPopWindowController.RefreshRoleInfo` calls it at
`0xc0514a0` with the avatar template ID in w0 and 1 in w1, then passes
the returned managed string to the game text widget. This branch looks
up the avatar name through `0xf833040` and `0xe81a774`.
`GPPMPHICDEA.FLMNMKCEGID` at `0x105ad1b8` accepts a managed text key
in x0 and the default option 0 in w1, as at `0xf5902a0` in
`UIActivityRoleSkinAwardPopWindowController.RefreshRewardTextInfo`.
It forwards to the game's text service. Both helper bodies match between
the reviewed original and installed frameworks.

The plugin uses these byte-checked functions during the main-thread
overlay refresh. It translates key-shaped strings, copies the result and
caches the label by roster ID until reset. A missing label falls back to
the roster ID. The dynamic labels still need a live check.

The damage display controller registers listeners for event IDs 545, 546
and 547 through `0xba010fc`. Cross-references lead upstream to the
publisher at `0xc38a864`. Several producers publish 545 with a combat
result object. For example, `0xd33b9d8` resolves a target, copies its runtime
ID into the published wrapper, and sets amount-related fields on the nested
result before publishing. `DHDAFGOCHEP.DPGGDNOKFHB` at `0xe2206e0` also
publishes 545 using this wrapper. This is a candidate for tracing the
original attacker and owner before the UI formats the result. A common event
number alone does not prove all producers represent applied HP damage.

For an independent amount check, `FEntityHPChangeAction.OnFighter_PropertyValueChanged`
at `0xb0ac41c` receives two double values and resolves a fighter handle.
The inspected callback uses those values in HP calculations. The
`MusicBattleSubSystem` property callback at `0xb961368` independently
subtracts the two double values. Neither inspected path establishes a stable
attacker identity. Compare the combat result against HP transitions on a
controlled hit, and follow the result's source or owner to its roster
template before changing meter attribution.

The session that exposed inflated totals contained seven adjacent pairs
with identical source, target, raw amount and kind within one millisecond.
It also contained individual payloads above two million. These observations
are insufficient to distinguish duplicates and combined values from valid
multi-hit damage. The meter labels the display feed as raw and applies no
timing-based deduplication.
