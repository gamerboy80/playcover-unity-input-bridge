import contextlib
import io
import importlib.util
from pathlib import Path
import struct
import unittest
import copy
import json
import plistlib
import shutil
import tempfile
from unittest.mock import patch

from profiles import load_profile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('zzz_patch', ROOT / 'patch.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PatchTests(unittest.TestCase):
    def test_profiles_list_copyable_commands_regular_before_test(self):
        with patch('sys.argv', ['patch.py', 'profiles']), contextlib.redirect_stdout(io.StringIO()) as out:
            module.main()
        output = out.getvalue()
        self.assertIn('python3 patch.py apply --profile hsr\n', output)
        self.assertIn('python3 patch.py apply --profile hsr-test\n', output)
        self.assertLess(output.index('--profile hsr\n'), output.index('--profile hsr-test\n'))

    def test_apply_alias_invokes_install(self):
        profile = copy.deepcopy(load_profile('hsr'))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app, _ = self.fake_app(root, profile)
            local = root / '.local' / profile['id']
            with patch.object(module, 'select_profile', return_value=profile), \
                    patch.object(module, 'local_directory', return_value=local), \
                    patch.object(module, 'install') as install, \
                    patch('sys.argv', ['patch.py', 'apply', '--profile', 'hsr', '--app', str(app)]):
                module.main()
            install.assert_called_once_with(app.resolve(), profile, local)

    def test_unknown_version_resolution_keeps_explicit_version_selection_strict(self):
        for game in ('zzz', 'hsr', 'hsr-test'):
            source = load_profile(game)
            detected = copy.deepcopy(source)
            detected.update(id=source['bundle_id'] + '-9.9.9-auto', version='9.9.9')
            with tempfile.TemporaryDirectory() as tmp:
                app, _ = self.fake_app(Path(tmp), copy.deepcopy(detected))
                for alias, automatic in [(game, True), (source['id'], False)]:
                    with self.subTest(alias=alias), \
                            patch.object(module, 'select_profile', side_effect=RuntimeError('This app does not match')), \
                            patch.object(module, 'resolve_app_profile', return_value=detected) as resolve, \
                            patch.object(module, 'install') as install, \
                            patch('sys.argv', ['patch.py', 'apply', '--profile', alias, '--app', str(app)]):
                        if automatic:
                            module.main()
                            resolve.assert_called_once_with(app.resolve(), module.read_app_info(app), source)
                            self.assertEqual(install.call_args.args[1], detected)
                        else:
                            with self.assertRaisesRegex(RuntimeError, 'does not match'):
                                module.main()
                            resolve.assert_not_called()
                            install.assert_not_called()

    def test_restore_with_app_uses_detected_active_profile(self):
        profile = copy.deepcopy(load_profile('hsr'))
        test_profile = copy.deepcopy(load_profile('hsr-test'))
        with tempfile.TemporaryDirectory() as tmp:
            app, _ = self.fake_app(Path(tmp), profile)
            local = Path(tmp) / '.local' / test_profile['id']
            state = {'profile': test_profile['id'], 'app': str(app), 'status': 'installed'}
            with patch.object(module, 'select_profile', return_value=profile), \
                    patch.object(module, 'applied_profile', return_value=(test_profile, state, local, 'installed')), \
                    patch.object(module, 'restore') as restore, \
                    patch('sys.argv', ['patch.py', 'restore', '--app', str(app)]):
                module.main()
            restore.assert_called_once_with(app.resolve(), state, test_profile, local)

    def test_apply_reuses_verified_backup_after_restore(self):
        profile = copy.deepcopy(load_profile())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app, _ = self.fake_app(root, profile)
            local = root / '.local' / profile['id']
            backup = local / 'original'
            binary, framework, main = module.app_paths(profile)
            backup.mkdir(parents=True)
            shutil.copytree(app / framework, backup / framework, symlinks=True)
            shutil.copy2(app / main, backup / main)
            shutil.copytree(app / '_CodeSignature', backup / '_CodeSignature')
            original = {path: module.digest(backup / path) for path in (binary, main)}
            (local / 'state.json').write_text(json.dumps({
                'profile': profile['id'], 'app': str(app), 'original': original,
                'installed': {}, 'status': 'restored',
            }))
            backup_hash = module.digest(backup / binary)
            with patch.object(module, 'ROOT', root), patch.object(module, 'closed'), \
                    patch.object(module, 'build'), patch.object(module, 'run'), \
                    patch.object(module, 'clone_app', side_effect=lambda source, target: shutil.copytree(source, target, symlinks=True)):
                module.install(app, profile, local)
            state = json.loads((local / 'state.json').read_text())
            self.assertEqual(state['status'], 'installed')
            self.assertEqual({p: state['original'][p] for p in original}, original)
            self.assertEqual({p: state['original'][p] for p in module.signature_hashes(backup, profile)},
                             module.signature_hashes(backup, profile))
            self.assertFalse((backup / binary).exists())
            self.assertEqual(module.hashlib.sha256(module.original_framework(app, profile, local)).hexdigest(), backup_hash)

    def test_input_restore_preserves_zzmi_installed_before_it(self):
        profile = copy.deepcopy(load_profile())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app, _ = self.fake_app(root, profile)
            _, _, main = module.app_paths(profile)
            metal_path = module.bridge_registry.OWNERS['zzmi-metal']
            (app / main).write_bytes(module.add_dylib(bytearray((app / main).read_bytes()), metal_path))
            (app / 'Frameworks/ZZMIMetal.dylib').write_bytes(b'metal bridge')
            module.bridge_registry.load(app, profile['bundle_id'], profile['version'], main)
            local = root / '.local' / profile['id']
            with patch.object(module, 'ROOT', root), patch.object(module, 'closed'), \
                    patch.object(module, 'build'), patch.object(module, 'run'), \
                    patch.object(module, 'clone_app', side_effect=lambda source, target: shutil.copytree(source, target, symlinks=True)):
                module.install(app, profile, local)
                state = json.loads((local / 'state.json').read_text())
                self.assertTrue(module.has_dylib((app / main).read_bytes(), module.LOAD_PATH))
                module.restore(app, state, profile, local)
            final = (app / main).read_bytes()
            self.assertFalse(module.has_dylib(final, module.LOAD_PATH))
            self.assertTrue(module.has_dylib(final, metal_path))
            self.assertTrue((app / 'Frameworks/ZZMIMetal.dylib').is_file())

    def test_input_restore_preserves_zzmi_installed_after_it(self):
        profile = copy.deepcopy(load_profile())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app, _ = self.fake_app(root, profile)
            _, _, main = module.app_paths(profile)
            local = root / '.local' / profile['id']
            with patch.object(module, 'ROOT', root), patch.object(module, 'closed'), \
                    patch.object(module, 'build'), patch.object(module, 'run'), \
                    patch.object(module, 'clone_app', side_effect=lambda source, target: shutil.copytree(source, target, symlinks=True)):
                module.install(app, profile, local)
                state = json.loads((local / 'state.json').read_text())
                registry = module.bridge_registry.load(app, profile['bundle_id'], profile['version'], main)
                owners = module.bridge_registry.owners_in((app / main).read_bytes())
                metal_path = module.bridge_registry.OWNERS['zzmi-metal']
                owners['zzmi-metal'] = metal_path
                with tempfile.TemporaryDirectory() as stage_dir:
                    staged = Path(stage_dir) / app.name
                    shutil.copytree(app, staged, symlinks=True)
                    staged_main = staged / main
                    staged_main.write_bytes(module.bridge_registry.compose(registry, owners))
                    shutil.copystat(app / main, staged_main)
                    (staged / 'Frameworks/ZZMIMetal.dylib').write_bytes(b'metal bridge')
                    module.bridge_registry.begin(registry, owners, staged)
                    module.replace_file(staged / main, app / main)
                    module.replace_file(staged / 'Frameworks/ZZMIMetal.dylib', app / 'Frameworks/ZZMIMetal.dylib')
                    module.bridge_registry.finish(registry, app)
                module.check_installed(app, state, profile)
                module.restore(app, state, profile, local)
            final = (app / main).read_bytes()
            self.assertFalse(module.has_dylib(final, module.LOAD_PATH))
            self.assertTrue(module.has_dylib(final, metal_path))
            self.assertTrue((app / 'Frameworks/ZZMIMetal.dylib').is_file())

    def test_status_labels(self):
        for name in ('zzz', 'hsr', 'zzz-test', 'hsr-test'):
            profile = load_profile(name)
            for status, expected in [('installed', f'Patched ({name})'),
                                     ('restored', 'Unpatched'), ('unpatched', 'Unpatched')]:
                with self.subTest(profile=name, status=status), contextlib.redirect_stdout(io.StringIO()) as out:
                    module.print_status({'status': status}, profile, Path('/unused'))
                    self.assertIn(f'Status: {expected}\n', out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as out:
            module.print_status({'status': 'prepared'}, load_profile(), Path('/unused'))
            self.assertNotIn('Status: Unpatched', out.getvalue())

    def test_status_without_saved_installation(self):
        profile = copy.deepcopy(load_profile())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app, _ = self.fake_app(root, profile)
            with patch.object(module, 'select_profile', return_value=profile), \
                    patch.object(module, 'local_directory', return_value=root / '.local'), \
                    patch('sys.argv', ['patch.py', 'status', '--app', str(app)]):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    module.main()
                self.assertIn('Status: Unpatched\n', out.getvalue())
                (app / profile['framework_binary']).write_bytes(b'changed')
                with self.assertRaisesRegex(RuntimeError, 'Cannot determine patch status safely'):
                    module.main()

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

    def signed_executable(self, signature):
        binary = self.executable()
        struct.pack_into('<II', binary, 16, 3, 240)
        struct.pack_into('<II16s4Q4I', binary, 184, 0x19, 72, b'__LINKEDIT',
                         4096, 4096, 1024, len(signature), 1, 1, 0, 0)
        struct.pack_into('<4I', binary, 256, 0x1d, 16, 1024, len(signature))
        return binary + signature

    def test_registered_resigning_comparison_preserves_code_checks(self):
        a = self.signed_executable(b'a' * 32)
        b = self.signed_executable(b'b' * 64)
        self.assertEqual(module.executable_content(a), module.executable_content(b))
        b[600] ^= 1
        self.assertNotEqual(module.executable_content(a), module.executable_content(b))
        with self.assertRaisesRegex(RuntimeError, 'end of the file'):
            module.executable_content(a + b'unsigned appended data')

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
                    patch.object(module, 'build'), patch.object(module, 'run'), \
                    patch.object(module, 'clone_app', side_effect=lambda source, target: shutil.copytree(source, target, symlinks=True)):
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
                    if '--force' in args and args[-1].endswith(app.name):
                        (Path(args[-1]) / '_CodeSignature/CodeResources').write_bytes(b'failed signature')
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

    def test_alias_state_is_preserved_and_duplicate_states_are_rejected(self):
        profile = copy.deepcopy(load_profile('hsr'))
        with tempfile.TemporaryDirectory() as tmp, patch.object(module, 'ROOT', Path(tmp)):
            app, _ = self.fake_app(Path(tmp), profile)
            _, _, main = module.app_paths(profile)
            (app / main).write_bytes(module.link_library(bytearray((app / main).read_bytes())))
            (app / module.LIBRARY).write_bytes(b'input bridge')
            module.bridge_registry.load(app, profile['bundle_id'], profile['version'], main)
            local = Path(tmp) / '.local' / 'hsr'
            local.mkdir(parents=True)
            state = {'profile': 'hsr', 'app': str(app),
                     'installed': {**module.signature_hashes(app, profile),
                                   main: module.digest(app / main),
                                   module.LIBRARY: module.digest(app / module.LIBRARY)},
                     'original': {profile['framework_binary']: profile['original_sha256']}}
            (local / 'state.json').write_text(json.dumps(state))
            self.assertEqual(module.local_directory(profile), local)
            module.check_installed(app, state, profile)
            canonical = local.parent / profile['id']
            canonical.mkdir()
            (canonical / 'state.json').write_text(json.dumps(state))
            with self.assertRaisesRegex(RuntimeError, 'Multiple matching'):
                module.local_directory(profile)

    def test_rejects_wrong_architecture(self):
        source = self.executable()
        struct.pack_into('<I', source, 4, 0x1000007)
        with self.assertRaisesRegex(RuntimeError, 'arm64'):
            module.link_library(source)

    def test_corrupt_state_raises_readable_error(self):
        profile = load_profile()
        with tempfile.TemporaryDirectory() as tmp, patch.object(module, 'ROOT', Path(tmp)):
            state_dir = Path(tmp) / '.local' / profile['id']
            state_dir.mkdir(parents=True)
            state_path = state_dir / 'state.json'
            state_path.write_text('{not valid json')
            with self.assertRaisesRegex(RuntimeError, "Couldn't read saved patch information"):
                module.local_directory(profile)
            state_path.write_text('[]')
            with self.assertRaisesRegex(RuntimeError, 'unexpected format'):
                module.local_directory(profile)

    def test_applied_profile_rejects_installed_plus_changed_conflict(self):
        primary = load_profile('zzz')
        secondary = load_profile('zzz-test')
        with tempfile.TemporaryDirectory() as tmp, patch.object(module, 'ROOT', Path(tmp)), \
                patch.object(module, 'profile_paths', return_value=[
                    ROOT / 'profiles' / f"{primary['id']}.json",
                    ROOT / 'profiles' / f"{secondary['id']}.json",
                ]):
            app, _ = self.fake_app(Path(tmp), primary)
            _, _, main = module.app_paths(primary)
            (app / main).write_bytes(module.link_library(bytearray((app / main).read_bytes())))
            (app / module.LIBRARY).write_bytes(b'input bridge')
            module.bridge_registry.load(app, primary['bundle_id'], primary['version'], main)
            primary_dir = Path(tmp) / '.local' / primary['id']
            primary_dir.mkdir(parents=True)
            primary_state = {
                'profile': primary['id'],
                'app': str(app),
                'status': 'installed',
                'installed': {**module.signature_hashes(app, primary),
                              main: module.digest(app / main),
                              module.LIBRARY: module.digest(app / module.LIBRARY)},
                'original': {primary['framework_binary']: primary['original_sha256']},
            }
            (primary_dir / 'state.json').write_text(json.dumps(primary_state))
            secondary_dir = Path(tmp) / '.local' / secondary['id']
            secondary_dir.mkdir(parents=True)
            (secondary_dir / 'state.json').write_text(json.dumps({
                'profile': secondary['id'],
                'app': str(app),
                'status': 'prepared',
                'original': {secondary['framework_binary']: secondary['original_sha256']},
            }))
            info = plistlib.loads((app / 'Info.plist').read_bytes())
            with self.assertRaisesRegex(RuntimeError, 'More than one profile matches'):
                module.applied_profile(app, info)


if __name__ == '__main__':
    unittest.main()
