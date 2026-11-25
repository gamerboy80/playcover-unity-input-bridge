# Veritas PlayCover port

The source reference is the local upstream Veritas 0.2.58 checkout. Adapted
aggregation, export fields, palette and translations retain the upstream MIT
notice in `plugins/veritas/UPSTREAM-LICENSE`. The backend here is ARM64 Catalyst;
upstream's Windows detours and DirectX renderer cannot be used in this process.

## Lookup and binary identity

Both plugin stagers now use the same `signatures.Image`, managed metadata and
native method-table resolvers as the desktop input installer. HSR's managed callable
methods and detoured entries are resolved by class/method name, with independent
native instruction checks. ZZZ's event hooks and identified helper methods use
managed names and registration anchors; remaining obfuscated helpers use unique
native signatures. Three internal IL2CPP helpers use native signatures.
Missing names, overload ambiguity, duplicate native matches,
changed metadata or native checks stop staging.

Resolution runs before writing the preview. The resulting bindings must reproduce
the reviewed JSON ABI. This is build-time discovery, not runtime reflection:
generated headers contain the resolved bindings, and runtime callbacks are
published only after validating the staged detours. It does not automatically
approve a future build's fields or calling conventions. Cave reservations and
object offsets remain exact-build JSON data. This distinction is deliberate:
a function name or matching entry cannot validate an object's layout.

An existing desktop-input installation is accepted only if the main installer's
active-state and installed-file checks pass and its hash-verified reconstructed
original is a reviewed plugin build. Its live hash is allowed for that operation
only; the checked-in hash allowlist is unchanged. Signature lookup still checks
the live callable methods. No backup or installed app is modified.

Stagers reject non-stack instructions in displaced prologues, entry/cave/slot
overlaps, occupied TEXT padding, section overlaps and non-zero-fill callback
storage. HSR now checks full stub bytes and empty callback slots before
registering any hook, and checks native helper signatures at runtime too.
Source and planned framework hashes are saved before modifying the isolated
copy. Codesigning and strict verification finish before publishing the copy.

## HSR 4.7.0 evidence

Addresses below are preferred VM addresses, mapped through Mach-O segments for
file access. HSR managed identities were recovered through the MHY metadata
contract, then inspected with bounded ARM64 disassembly. Full dumps remain local.

| Identity | VM | Contract |
| --- | --- | --- |
| `BattleInstance..ctor` | `0x26540b8` | this, configuration pointer, lineup pointer, int, uint, bool, hidden method context |
| `TurnBasedAbilityComponent.ProcessOnLevelTurnActionEndEvent` | `0x281f8ac` | this, int, hidden context; complete the open turn once |
| `TurnBasedGameMode.UpdateCurrentWaveCount` | `0x283885c` | this, hidden context; query the reviewed wave getter after original |
| `TurnBasedGameMode.get_ChallengeTurnLeft` | `0x283f204` | uint return; preserve the original result |
| `TurnBasedGameMode.ResetAllEntityActionDelay` | `0x2831b84` | this, hidden context; record the elapsed-AV baseline after original |
| `TurnBasedAbilityComponent.DirectChangeHP` | `0x2811dc8` | this, modify-function enum, FixPoint, context pointer, strength enum, hidden context |
| `TurnBasedAbilityComponent.ModifyProperty` | `0x2807390` | this, property enum, function enum, FixPoint, context pointer, hidden context; bool return |
| `MonsterDataComponent.OnAbilityCharacterInitialized` | `0x278b510` | this, ability component, hidden context |
| `CharacterDataComponent.OnAbilityCharacterInitialized` | `0x2662d50` | this, ability component, hidden context |
| `TeamFormationComponent._RefreshTeammateIndex` | `0x27ed180` | this, hidden context |

The original damage, battle, turn and skill mappings remain in
`plugins/veritas/hsr-4.7.0.json`. Typed skill-row `get_AttackType` getters are now
resolved alongside their localized-name getters. The checked property indices
are recorded under `properties` in that profile. Runtime `Enum.GetNames` and
`Enum.GetValues` provide the complete property/category mapping; capture refuses
to start if the independently checked HP, speed and AV indices disagree.

Two errors in the previous port are corrected:

- `GetProperty(1)` is **MaxHP**, not CurrentHP. `DirectDamageHP` reads the property
  array at ability `+0xc8`, checks index 10, loads entry `+0x70`, and reads its
  FixPoint at property `+0x60` before subtracting incoming damage. CurrentHP is
  therefore index 10. `MonsterDataComponent.OnAbilityCharacterInitialized` calls
  `GetProperty(1)` at `0x278b70c` and stores the initial maximum at `+0x190`.
- `DirectDamageHP` takes a 16-byte `Nullable<FixPoint>` in x5/x6. Its entry saves
  both registers together at `0x2811154`; x7 is the integerization enum, with the
  hidden context on the stack. The former single-pointer declaration shifted
  those arguments. The wrapper now forwards a two-word struct and a void return.

`GetProperty` independently special-cases Attack 18 and Defence 23. The named
`RefreshSpeed` path modifies property 32, and `SetupActionDelayByUnitDistance`
reads 32 and modifies property 38. ActionDelay values are converted to AV by 10.
The remaining indices are named through the runtime enum arrays, without using
Windows enum ordinals.

The native lineup copy and `FillAliveLightTeam` access the LightTeam array at
`+0x20`, array length at `+0x18`, and elements at `+0x20`. `LineUpCharacter.DeepCopy`
and lineup membership checks access CharacterID at `+0x6c`. ExtraTeam is read by field name through `RuntimeType.GetFields` and
`MonoField.GetValue`; no ExtraTeam offset is assumed. Additional player
entities are also added when their ability initialization is observed. `_RefreshTeammateIndex` uses the formation list at
`+0xa8`, list items at `+0x10`, count at `+0x18`, and formation owner at `+0x10`.
All reads are bounded by array/list counts and retain no game pointers on the
UI queue. `SkillConfigID` and property-icon `IconPath` are also read through
field reflection; formation updates are restricted to the reflected TeamDark
component, and boxed skill IDs must identify as UInt32 before their value
is copied. The boxed value begins at the reviewed 16-byte object header. The string and FixPoint layouts retain their existing reviewed ABI.

## Behavior compared with upstream

The port includes automatic character/enemy portraits, the character DMG/DPAV meter, gray overkill segments, damage
bars and distribution, attack-category pie/bar views with team/character scope,
legend/table toggles, turn/AV graphs, character legend, metrics, enemy HP,
formation updates, property changes, skill details and console. Panels retain
the upstream compact dark styling and character colors, with editable saved
positions/sizes. It also exposes the upstream translation catalog, palette/light
mode, custom accent, font size, pie/window opacity, auto-hide, streamer message,
exports, date folders and automatic end-of-battle saving.

Gross damage and overkill are separate, as upstream. Skill totals follow the
most recent manual skill **for that owner**, including delayed damage. That is
upstream's grouping heuristic, not causal identification of the delayed skill.
Direct HP loss without an attacker remains separate from character totals.
The inactive upstream combo/defeat detours are not enabled speculatively.

JSON exports use upstream's camel-case schema, with the richer local capture in
`_playcover`. CSV includes the upstream character-summary and skill-detail
columns. A bounded event journal reports dropped entries explicitly. Battle
history keeps the last 50 results; charts do not truncate the export's turns or
skills. The console displays its last 200 messages.

The loopback server implements Socket.IO/Engine.IO v4 polling and WebSocket at
`127.0.0.1:1305`. It sends `Connected` and the active combat packets, with
Engine.IO pings, session expiry, client/connection limits and bounded queues.
Both direct WebSocket sessions and polling-to-WebSocket probe upgrades are supported. A stalled client's overflowing queue
closes the session instead of silently presenting an incomplete stream. It
never uploads combat data; an external analysis client is a separate choice.
Upstream's older `docs/API.md` describes an obsolete framed protocol; the
reference for this port is its actual `server.rs` and `models/packets.rs`.

## Remaining platform differences and validation

Portraits use the reviewed `AvatarHelper.GetSideIconPath` and
`MonsterRowData.get_RoundIconPath`, `CachedAssetLoader.SyncLoadAsset`,
`Sprite.get_texture`, RenderTexture temporary/active APIs, Graphics.Blit,
Texture2D construction/ReadPixels/Apply, and ImageConversion.EncodeToPNG.
The selected overloads are independently signature-checked. Render texture
format Default and read/write Linear are resolved by enum name too.

`System.Object.GetType` branches through `0xf2d3d10`, which loads the object's
class and passes class `+0x68` to the runtime type-object helper at `0xf315180`.
The existing metadata type loader resolves the actual classes for AbilityProperty,
AttackType, Sprite, Texture2D, AvatarPropertyType and the render-format enums. Two metadata
classes are named Sprite; the class declaring the independently resolved
`get_texture` method selects the Unity class. Missing or ambiguous class evidence
stops resolution.

Texture2D.CreateExternalTexture demonstrates allocation through `0xf2c7898`,
which tail-branches through `0xf313798` to the allocator at `0xf31387c`. It takes
an Il2CppClass pointer; the conversion resolves the class declaring the verified
Texture2D constructor, allocates it, then invokes that two-argument constructor. The four-float
ReadPixels rect uses the ARM64 HFA convention. Temporary/readable resources are
released/destroyed and the **pre-Blit** render target is restored even when
conversion throws. This corrects the upstream sequence that samples the active
target only after Blit. PNG data is copied before reaching the UI queue, bounded
to 16 MiB, and decoded into a bounded image cache. No Unity object pointer is
retained in Objective-C UI state.

Optional local PNG portraits can override a missing conversion under the game's
`Documents/Veritas/Portraits/avatars/<avatar-id>.png` or
`.../enemies/<monster-template-id>.png`; otherwise the UI uses initials/text.
Upstream's Windows binary self-updater is replaced by a release-information check
and native rebuild instructions. The Socket.IO event API supports polling and WebSocket, including transport
upgrades. It follows the [Engine.IO](https://socket.io/docs/v4/engine-io-protocol/)
and [Socket.IO](https://socket.io/docs/v4/socket-io-protocol/) packet conventions. Native UIKit controls replace DirectX/egui
controls. These platform differences are explicit.

The local HSR 4.7.0 and ZZZ 3.3.1 fixtures resolved all 76 and 15 plugin
functions, respectively. Both preview apps, frameworks and plugins passed
strict signature verification. The source framework hashes matched the
previews' staging plans after preparation. The synthetic overlay preview and
native tests cover aggregation, exports, portrait conversion cleanup and the
Socket.IO transports.

Live validation still requires an operator-controlled game session for the new
combat hooks, enum and field reflection, portraits, support units, AV and wave
transitions, summon attribution, native text editing and menus. ZZZ retains its
existing attribution and damage-feed limits in `zzz-damage-probe.md`.
