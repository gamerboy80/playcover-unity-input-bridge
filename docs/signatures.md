# Automatic version detection

`patch.py apply --profile zzz` selects a reviewed profile when one matches. For an
unknown version it tries the ZZZ signature contract before building. An explicitly
versioned profile never silently changes its target version. `resolve --app APP`
performs detection without changing the app. `--profile zzz-test` selects the
experimental platform/settings variant.

## Checks

1. Verify the bundle ID, executable, thin ARM64 image, encryption status, Mach-O
   segments and function boundaries. Read an installed patch's verified original
   backup when resolving an already patched build.
2. Locate the metadata string, type and method tables through multiple sentinel
   records. The resolver recognizes the examined record layout without using
   fixed table addresses or trusting encrypted header offsets.
3. Resolve methods by namespace, class, name and parameter count. Locate the
   corresponding native module registration. Test candidate pointer tables and
   token indexing against every required method's native signature. Accept only
   one set of resolved addresses.
4. Mask relocation operands in ARM64 signatures while preserving opcodes and
   register relationships. Independent C++ functions require a unique match in
   executable code. Managed functions also require metadata identity and a real
   function entry.
5. Decode field offsets from named getters and static storage references. Check
   instruction forms, register chains, alignment and bounds. Mouse, Keyboard and
   InputSystem must independently resolve the same static-storage pointer.
   Distinguish VM addresses, file offsets and zero-filled writable data.
6. Locate each byte edit inside its verified function. Validate its opcode mask,
   record the actual original bytes and calculate the PC predicate's return
   branch from its verified epilogue. Preserve the Unity predicate branch.
7. Save the resolved profile, framework SHA-256, metadata SHA-256, contract ID,
   method addresses and extraction evidence before installation. Standard backup,
   signing, independent-file-change and restore checks still apply.

The contract lives in `signatures/com.HoYoverse.Nap.json`. It contains authored
method identities and instruction signatures, not game binaries or metadata
dumps. The same resolver produces the regular and experimental profile edits.
Local profile IDs include the game version, variant and a signature-contract digest
(`-auto-<digest>` or `-platform-pc-settings-auto-<digest>-test`). This keeps
contract revisions separate without overwriting previously resolved profiles.
Generated profiles stay outside tracked source.

## Limits

The first contract recognizes ZZZ's examined metadata record layout and input
backend. Obfuscated selector names, metadata layout, instruction shapes and the
input ABI can change. The resolver stops when it cannot prove a match. It does
not select the nearest match or reuse old offsets.

Keyboard state format, extended Mouse payload size and native calling conventions
remain backend contracts. Runtime device validation disables the bridge on an
unexpected Mouse format or size. Static resolution does not prove gameplay or
menu behavior. A generated profile records `runtime_validated: false`.

New metadata formats, renamed obfuscated selectors or a different backend require
research and a contract update. HSR and Endfield still use reviewed exact-build
profiles. Automatic detection is not a promise that arbitrary updates or games
will work.

## Validation

Synthetic tests cover relocated methods, changed field offsets, missing methods,
wrong native code, duplicate metadata tables, ambiguous scans, ARM64 register
chains and VM/file mappings. The optional local fixture test reconstructs both
reviewed ZZZ 3.3.1 profiles and compares every address, field, edit and framework
hash. Set `ZZZ_ORIGINAL_FRAMEWORK` and `ZZZ_METADATA` to run it with local game
files. These files must never be committed.
