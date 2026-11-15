# Automatic version detection

`patch.py apply --profile zzz` selects a reviewed profile when one matches. For an
unknown version it tries the selected game’s signature contract before building. An explicitly
versioned profile never silently changes its target version. `resolve --app APP`
performs detection without changing the app. `--profile zzz-test` and `--profile hsr-test` select the
experimental platform/settings variants.

## Checks

1. Verify the bundle ID, executable, thin ARM64 image, encryption status, Mach-O
   segments and function boundaries. Read an installed patch's verified original
   backup when resolving an already patched build.
2. Locate the metadata string, type and method tables through multiple sentinel
   records. The resolver recognizes the examined record layout without using
   fixed table addresses or trusting encrypted header offsets.
3. Resolve methods by namespace, class, name and parameter count. Locate the
   corresponding native module registration. Verify candidate pointer tables
   with independent registration anchors and check that all required tokens
   lead to executable function entries. Accept only one set of addresses.
4. Mask relocation operands in ARM64 signatures while preserving opcodes and
   register relationships. Independent C++ functions require a unique match in
   executable code. After resolving managed identities, validate the required
   callback ABI and instructions. A validation failure reports that the method
   was found and its implementation changed.
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
The regular profile resolves only the methods it needs, so changes to the
experimental platform queries do not block regular detection. The resolver
extracts the state block offset from the verified getter and checks its range
and alignment. It also checks the input selector edit at the function entry.
Local profile IDs include the game version, variant and a signature-contract digest
(`-auto-<digest>` or `-platform-pc-settings-auto-<digest>-test`). This keeps
contract revisions separate without overwriting previously resolved profiles.
Generated profiles stay outside tracked source.

## Contract rules

Managed function rules specify their metadata identity. They can omit an entry
pattern. ZZZ uses `registration_anchor` on selected methods to establish its
native module table and token indexing. An anchor can search within a function
with `search: true`, allowing its relevant instructions to move.

After method lookup succeeds, `verify` checks a specific instruction sequence
when the bridge requires it. `abi: callback` decodes the callback slot,
checks writable storage, and verifies that the wrapper branches to the same
register that received the function pointer. The pointer address can change.
Existing contracts with entry `pattern` and `mask` remain supported.

Field extraction and byte patches run against the resolved functions. Their
local instruction checks, range checks, alignment checks and call destination
checks still apply. Metadata identity alone cannot establish field offsets or
which branch implements a platform check. Ambiguous native tables stop lookup
before subsequent implementation checks run.
Failures are collected within each stage, including independent field
extractions and patch sites. A failed stage prevents saving a generated profile.

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
research and a contract update. Endfield still uses reviewed exact-build
profiles. Automatic detection is not a promise that arbitrary updates or games
will work.

## Validation

Synthetic tests cover relocated methods, changed field offsets, missing methods,
wrong native code, duplicate metadata tables, ambiguous scans, ARM64 register
chains and VM/file mappings. The optional local fixture test reconstructs both
reviewed ZZZ 3.3.1 profiles and compares every address, field, edit and framework
hash. Set `ZZZ_ORIGINAL_FRAMEWORK` and `ZZZ_METADATA` to run it with local game
files. These files must never be committed.

## HSR contract

`signatures/com.HoYoverse.hkrpgoversea.json` covers both HSR 4.6.0 and 4.7.0 variants.
Use `resolve --profile hsr --app APP` or `resolve --profile hsr-test --app APP`
for read-only detection. The unversioned `hsr` and `hsr-test` aliases also attempt
resolution when applying to an unknown version; explicit versioned IDs stay strict.

For 4.7.0 and later candidates, the resolver locates the HSR metadata accessors
with masked ARM64 signatures, follows their table references and decodes class
and method names from the MHY records. It follows the native method index to
executable function entries, rejecting missing or ambiguous matches. The cursor
and menu rules check the actual destination of the original call. The verified
4.6.0 framework hash selects the earlier native-only rules.

Callback slots are decoded from verified ADRP/ADD/LDR register chains and must
land in writable data. Independent key wrappers must agree on the corresponding
slot. UI scroll return PCs must follow BLR inside their matched functions. The
mouse-processing call is encoded against the resolved ProcessMouseEvent function;
the cursor-mode branch is encoded against its matched destination. No old call
or branch displacement is carried into the new profile.

The legacy ABI and scroll scale remain the reviewed backend contract. Detection
must stop on missing, ambiguous or changed instruction shapes; it does not prove
future gameplay compatibility. A change to the metadata encoding, table accessors,
managed names or input ABI can require updating the contract. No game installation
or launch is needed for resolution.

Set `HSR_ORIGINAL_FRAMEWORK` to the 4.6.0 framework and `HSR_47_APP` to the
unpatched 4.7.0 app to run the optional local fixture checks. They compare
every bridge address, byte patch and framework hash for both variants.
For an installed patch, set `HSR_47_ORIGINAL_FRAMEWORK` to its saved original
framework while `HSR_47_APP` supplies the matching metadata.
