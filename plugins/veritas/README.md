# Veritas Live for PlayCover

Veritas Live charts player damage during combat in Honkai: Star Rail. The
overview shows cumulative damage, each character’s damage share, and damage by
turn. Separate panels show damage by attack type for each character and recent
skill uses. Each battle starts a new chart. The last result stays visible
unless automatic hiding is enabled.

- Press **⌘⇧D** to toggle the panels.
- Press **⌘⇧E** to edit the layout. Drag a panel by its title and resize it
  with the lower-right handle. Open a gear menu to show or hide the extra
  panels or set the theme, opacity, and text size. Position and settings are
  saved. Press **⌘⇧E** again to return pointer input to the game.
- Enable streamer mode in a gear menu to anonymize character labels and show
  a banner over the game’s usual UID area.

This preview targets the reviewed international **HSR 4.7.0** ARM64 build
(`com.HoYoverse.hkrpgoversea`). It uses the same event sources as the
[Veritas combat subscriber](https://github.com/hessiser/veritas/blob/main/src/subscribers/battle.rs)
for damage and manual skill use. Skill names come from the game’s text map.
A skill slot label appears when a localized name is unavailable. The meter
records skill use separately from the damage breakdown so delayed effects
do not inherit the next skill’s name. Standalone enemy HP loss without an
attacker is shown separately from character damage totals.

## Prepare and inject a preview

Use Apple Silicon, Xcode Command Line Tools, Python 3.11+, and PlayTools with
Custom Plugins support. Build the dylib and stage the hooks from the repository
root:

~~~sh
sh plugins/veritas/build.sh
python3 plugins/veritas/stage.py \
  --app "$HOME/Library/Containers/io.playcover.PlayCover/Applications/com.HoYoverse.hkrpgoversea.app" \
  --output build/plugins/HSR-Veritas-Preview.app --without-plugin
~~~

Install `build/plugins/VeritasLive.dylib` into the prepared copy using a plugin
loader you already use, or place it in the folder scanned by PlayTools and
re-sign the copy:

~~~sh
preview=build/plugins/HSR-Veritas-Preview.app
mkdir -p "$preview/Frameworks/UserPlugins"
cp build/plugins/VeritasLive.dylib "$preview/Frameworks/UserPlugins/"
codesign --force --sign - --preserve-metadata=entitlements "$preview"
codesign --verify --strict "$preview"
~~~

Omit `--without-plugin` if you want the staging command to place and sign the
dylib in the copy. Quit HSR before opening the preview. It uses the same
PlayCover data account and settings. The standalone dylib requires the framework
hooks, which are compatible with either reviewed framework hash, including the
current desktop input patch. Remove the old **VeritasReports** entry in
PlayCover’s Custom Plugins settings if it was added previously.

## Porting notes

`hsr-4.7.0.json` records supported framework hashes and reviewed addresses.
The managed metadata maps `PGOOHIHKHNJ.NNGMOCFGPBN` to the damage routine.
ARM64 register use matches Veritas's damage ABI, and the routine calls
`AbilityStatic.DamagePostProcess` and `AbilityStatic.TargetDamageHP`.
`AbilityStatic._MortallyWondedProcess` clears the four damage fields together
when it invalidates the result. `GetProperty` with property 1 is also used by
`DirectDamageHP` to read current HP. Battle start and end use
`TurnBasedGameMode._GameModeBegin` and `_GameModeEnd`. Turn samples come from
`DoTurnPrepareStartWork`, using the game’s elapsed action delay and current
wave getters. The name path uses `UIGameEntityUtils.GetAvatarID` and
`AvatarHelper.GetAvatarName` after resolving the owner or summoner. The damage setup copies the attack type
into the damage object at `0x204`. Skill history hooks
`SkillCharacterComponent.UseSkill` and resolves the typed skill row’s
`TextID` through `TextmapStatic.GetText`.

Staging verifies the exact native framework, copied entry instructions and
segment padding, then signs the isolated app copy. The detours forward to the
original routines while their callback slots are empty. PlayTools loads the
overlay, which registers callbacks only after checking the detoured entries.
