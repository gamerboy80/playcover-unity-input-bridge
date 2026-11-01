# HSR 4.6.0

Profile: `hsr`; bundle: `com.HoYoverse.hkrpgoversea`; executable: `hkrpg`.
Initialization was observed, but physical gameplay validation is pending.
The patched app reached its resource downloader (about 47 GB outstanding), which
currently prevents entering gameplay for input verification.

```sh
python3 patch.py install --profile hsr
python3 patch.py status --profile hsr
python3 patch.py update --profile hsr
python3 patch.py restore --profile hsr
```

Builds and backups are separate from ZZZ in `build/hsr/` and `.local/hsr/`.
Disable PlayCover keymapping and preserve the PlayTools pointer-lock fix.

## Analysis

Original framework SHA-256:
`29c5e8960e90bdd1f877f2b3e040deb965506325c922e826c80fee5840115dcd`.
Examined global metadata SHA-256:
`6ea5b6f3e444fd530c2d76ae89cae81d75a3eb80bcb4ab69cfee8ced2570e3cf`.
Startup metadata SHA-256:
`bc2ddd0ce7e9db6790a48e5d5e201094f31aef5c9d0070fae862e9431994b298`.

This metadata has an MHY header, body at `+0x208`, 70-byte type rows and 26-byte
method rows. Loader `0xea31894` and string decoder `0xea32848` were traced to
recover names and associate methods with native table `0x14b2c9f0`. 139 image
names were recovered, including InControl; ZZZ's Unity Input System assembly
was absent. InControl's Unity keyboard/mouse providers use legacy input here.

Two predicates return true: `AppUtils.IsPCLayout` at `0xf2bde8` and
`UIUtils.IsPCMode` at `0x226c378`. The profile records exact original bytes and
the replacement `mov w0,#1; ret`. These text VM addresses equal file offsets.
OS/network identity predicates are not changed. Other builds require new analysis.

## Backend

`unity-legacy-v1` shares AppKit monitoring, capture/focus fixes, key mapping and
trackpad conversion with ZZZ. `src/LegacyBackend.h` supplies game-facing input.
Keyboard changes call the verified `Input.SetKey(KeyCode,bool)` wrapper at
`0xe89c394`, which forwards to native SetKeyState; its SetKeyDown/SetKeyUp
wrappers explicitly pass true/false. Shared Unity Key indices are translated
to legacy UnityEngine.KeyCode values.

Mouse getters tail-call writable callback slots relative to VM `0x15a4f270`:

| Offset | Native signature / purpose |
| --- | --- |
| `+0xd78`, `+0xd80` | `float(IL2CppString *)`; GetAxis/GetAxisRaw |
| `+0xda0`, `+0xda8`, `+0xdb0` | `BOOL(int)`; mouse held/down/up |
| `+0xeb8` | `void(float[3])`; mouse position |
| `+0xec0` | `void(float[2])`; scroll |
| `+0xe20` | `BOOL(void)`; mouse present |

Apply the dyld slide to VM addresses. `Time.frameCount` at `0xe8732f4` defines
frame boundaries. Pending edges/deltas are published on the next frame's first
poll and remain stable across repeated reads. Unknown axes and native buttons
preserve original callbacks; position preserves the original until host input
arrives. Mouse X/Y currently use a provisional 0.05 scale, requiring calibration.

Tests exercise key translation/releases, per-frame button/scroll state, callback
installation and native fallback. Both backends build with warnings as errors.
Initialization and synthetic tests do not establish physical gameplay success.
