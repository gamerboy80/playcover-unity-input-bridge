import importlib.util
from pathlib import Path
import struct
import unittest
import copy
import json
import plistlib
import tempfile
from unittest.mock import patch

from profiles import load_profile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('zzz_patch', ROOT / 'patch.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PatchTests(unittest.TestCase):
    def test_instruction_changes_are_exact_and_reject_wrong_bytes(self):
        profile = {'patches': [
            {'file_offset': '0x4', 'expected': '61626364', 'replacement': '5758595a'},
            {'file_offset': '0x14', 'expected': '65666768', 'replacement': '31323334'},
        ]}
        source = bytearray(b'----abcd------------efgh----')
        result = module.patch_instructions(source.copy(), profile)
        self.assertEqual(result, b'----WXYZ------------1234----')
        source[4] = 0
        with self.assertRaisesRegex(RuntimeError, 'Unexpected instructions'):
            module.patch_instructions(source, profile)

    def executable(self):
        binary = bytearray(1024)
        struct.pack_into('<II', binary, 0, 0xfeedfacf, 0x100000c)
        struct.pack_into('<II', binary, 16, 1, 152)
        struct.pack_into('<II', binary, 32, 0x19, 152)
        struct.pack_into('<I', binary, 32 + 64, 1)
        struct.pack_into('<I', binary, 32 + 72 + 48, 512)
        binary[512:] = b'x' * 512
        return binary

    def test_load_command_uses_only_unused_header(self):
        source = self.executable()
        result = module.link_library(source.copy())
        self.assertEqual(result[512:], source[512:])
        count, size = struct.unpack_from('<II', result, 16)
        self.assertEqual(count, 2)
        cmd, length, name_offset = struct.unpack_from('<III', result, 184)
        self.assertEqual((cmd, name_offset), (0xc, 24))
        self.assertEqual(size, 152 + length)
        self.assertEqual(length % 8, 0)
        self.assertIn(b'@executable_path/Frameworks/NativeInputBridge.dylib\0', result[184:512])

    def test_rejects_nonzero_padding_truncated_commands_and_no_space(self):
        source = self.executable()
        source[190] = 1
        with self.assertRaisesRegex(RuntimeError, 'padding'):
            module.link_library(source)
        source = self.executable()
        struct.pack_into('<I', source, 36, 8)
        with self.assertRaisesRegex(RuntimeError, 'Truncated segment'):
            module.link_library(source)
        source = self.executable()
        struct.pack_into('<I', source, 32 + 72 + 48, 192)
        with self.assertRaisesRegex(RuntimeError, 'padding'):
            module.link_library(source)

    def fake_app(self, root, profile):
        app = root / 'game.app'
        binary, framework, main = module.app_paths(profile)
        (app / framework / '_CodeSignature').mkdir(parents=True)
        (app / '_CodeSignature').mkdir()
        (app / binary).write_bytes(b'----abcd----')
        (app / main).write_bytes(self.executable())
        (app / main).chmod(0o755)
        for relative in (framework + '/_CodeSignature/CodeResources', '_CodeSignature/CodeResources'):
            (app / relative).write_bytes(b'original signature')
        (app / 'Info.plist').write_bytes(plistlib.dumps({
            'CFBundleIdentifier': profile['bundle_id'],
            'CFBundleShortVersionString': profile['version'], 'CFBundleExecutable': main,
        }))
        profile['original_sha256'] = module.digest(app / binary)
        profile['patches'] = [{'file_offset': '0x4', 'expected': '61626364', 'replacement': '5758595a'}]
        bridge = root / 'build' / profile['id'] / 'NativeInputBridge.dylib'
        bridge.parent.mkdir(parents=True)
        bridge.write_bytes(b'bridge-v1')
        return app, bridge

    def test_profile_install_update_rollback_and_restore(self):
        profile = copy.deepcopy(load_profile())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app, bridge = self.fake_app(root, profile)
            local = root / '.local' / profile['id']
            binary, framework, main = module.app_paths(profile)
            original_main = (app / main).read_bytes()
            with patch.object(module, 'ROOT', root), patch.object(module, 'closed'), \
                    patch.object(module, 'build'), patch.object(module, 'run'):
                module.install(app, profile, local)
                state = json.loads((local / 'state.json').read_text())
                self.assertEqual(state['profile'], profile['id'])
                self.assertEqual((app / binary).read_bytes(), b'----WXYZ----')
                self.assertTrue((app / main).stat().st_mode & 0o111)
                self.assertEqual((app / module.LIBRARY).read_bytes(), b'bridge-v1')
                bridge.write_bytes(b'bridge-v2')
                module.update(app, state, profile, local)
                self.assertEqual((app / module.LIBRARY).read_bytes(), b'bridge-v2')
                state = json.loads((local / 'state.json').read_text())
                bridge.write_bytes(b'bad-build')

                def fail_app_sign(*args):
                    if '--force' in args and args[-1] == str(app):
                        (app / '_CodeSignature/CodeResources').write_bytes(b'failed signature')
                        raise RuntimeError('signing failed')

                with patch.object(module, 'run', side_effect=fail_app_sign):
                    with self.assertRaisesRegex(RuntimeError, 'signing failed'):
                        module.update(app, state, profile, local)
                self.assertEqual((app / module.LIBRARY).read_bytes(), b'bridge-v2')
                self.assertEqual((app / '_CodeSignature/CodeResources').read_bytes(), b'original signature')
                self.assertEqual(json.loads((local / 'state.json').read_text()), state)
                module.restore(app, state, profile, local)
                self.assertEqual((app / binary).read_bytes(), b'----abcd----')
                self.assertEqual((app / main).read_bytes(), original_main)
                self.assertFalse((app / module.LIBRARY).exists())

    def test_legacy_state_is_reused_only_for_matching_original(self):
        profile = load_profile()
        with tempfile.TemporaryDirectory() as tmp, patch.object(module, 'ROOT', Path(tmp)):
            local = Path(tmp) / '.local'
            local.mkdir()
            (local / 'state.json').write_text(json.dumps({
                'original': {profile['framework_binary']: profile['original_sha256']},
            }))
            self.assertEqual(module.local_directory(profile), local)
            other = dict(profile, id='other-game-1.0', original_sha256='0' * 64)
            self.assertEqual(module.local_directory(other), local / other['id'])
            with self.assertRaisesRegex(RuntimeError, 'Profile does not match'):
                module.check_installed(Path('/unused'), {'original': {}}, profile)

    def test_rejects_wrong_architecture(self):
        source = self.executable()
        struct.pack_into('<I', source, 4, 0x1000007)
        with self.assertRaisesRegex(RuntimeError, 'arm64'):
            module.link_library(source)


if __name__ == '__main__':
    unittest.main()
