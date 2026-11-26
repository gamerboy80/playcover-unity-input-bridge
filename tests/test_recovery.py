import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_patch as fixtures
from profiles import load_profile, validate

module = fixtures.module


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.profile = copy.deepcopy(load_profile())
        self.app, self.bridge = fixtures.PatchTests().fake_app(self.root, self.profile)
        self.local = self.root / '.local' / self.profile['id']
        for name in ('ROOT', 'closed', 'build', 'run'):
            mocked = patch.object(module, name, self.root) if name == 'ROOT' else patch.object(module, name)
            mocked.start()
            self.addCleanup(mocked.stop)
        clone = patch.object(module, 'clone_app',
                             side_effect=lambda source, target: fixtures.shutil.copytree(source, target, symlinks=True))
        clone.start()
        self.addCleanup(clone.stop)
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def state(self):
        return json.loads((self.local / 'state.json').read_text())

    def install(self):
        module.install(self.app, self.profile, self.local)

    def test_confirmed_profile_switch_restores_then_installs_and_can_switch_back(self):
        requested = copy.deepcopy(self.profile)
        requested['id'] += '-switch-test'
        requested['test_only'] = True
        requested['patches'][0]['replacement'] = '31323334'
        profiles = {p['id']: p for p in (self.profile, requested)}
        (self.root / 'profiles').mkdir()
        for name in profiles:
            (self.root / 'profiles' / (name + '.json')).write_text('{}')
        new_bridge = self.root / 'build' / requested['id'] / 'NativeInputBridge.dylib'
        new_bridge.parent.mkdir(parents=True)
        new_bridge.write_bytes(b'test profile bridge')
        new_local = self.root / '.local' / requested['id']
        binary = self.app / self.profile['framework_binary']
        original = binary.read_bytes()
        with patch.object(module, 'load_profile', side_effect=profiles.__getitem__), \
                patch('builtins.input', return_value=' YES ') as confirm:
            self.install()
            confirm.assert_not_called()
            module.install(self.app, requested, new_local)
            self.assertEqual(self.state()['status'], 'restored')
            switched = json.loads((new_local / 'state.json').read_text())
            self.assertEqual(switched['status'], 'installed')
            self.assertEqual(switched['profile'], requested['id'])
            self.assertEqual(binary.read_bytes(), b'----1234----')
            self.assertEqual((self.app / module.LIBRARY).read_bytes(), b'test profile bridge')
            self.assertEqual(module.original_framework(self.app, requested, new_local), original)
            prompt = confirm.call_args.args[0]
            self.assertIn(module.profile_name(self.profile), prompt)
            self.assertIn(requested['id'], prompt)
            self.assertIn('[y/N]', prompt)
            confirm.return_value = 'y'
            self.install()
            self.assertEqual(confirm.call_count, 2)
        self.assertEqual(self.state()['status'], 'installed')
        self.assertEqual(json.loads((new_local / 'state.json').read_text())['status'], 'restored')
        self.assertEqual(binary.read_bytes(), b'----WXYZ----')

    def test_declined_or_interrupted_profile_switch_does_not_change_files(self):
        requested = dict(self.profile, id=self.profile['id'] + '-switch-test')
        before = {str(p.relative_to(self.root)): module.digest(p)
                  for p in self.root.rglob('*') if p.is_file()}
        for answer in ('', 'n', 'no', 'maybe', EOFError(), KeyboardInterrupt()):
            with self.subTest(answer=answer), \
                    patch.object(module, 'applied_profile', return_value=(self.profile, {}, self.local, 'installed')), \
                    patch.object(module, 'restore') as restore, \
                    patch('builtins.input', return_value=answer if isinstance(answer, str) else None,
                          side_effect=None if isinstance(answer, str) else answer):
                module.install(self.app, requested, self.root / '.local' / requested['id'])
                restore.assert_not_called()
                module.build.assert_not_called()
                self.assertEqual({str(p.relative_to(self.root)): module.digest(p)
                                  for p in self.root.rglob('*') if p.is_file()}, before)

    def test_profile_switch_keeps_same_profile_and_recovery_guards(self):
        for status, requested, error in (
                ('installed', self.profile, 'already applied'),
                ('changed', dict(self.profile, id='other'), 'needs attention'),
                ('prepared', dict(self.profile, id='other'), 'needs attention'),
                ('restoring', dict(self.profile, id='other'), 'needs attention'),
                ('installed', dict(self.profile, id='other', original_sha256='0' * 64), 'different game binary')):
            with self.subTest(status=status, requested=requested['id']), \
                    patch.object(module, 'applied_profile', return_value=(self.profile, {}, self.local, status)), \
                    patch('builtins.input') as confirm, patch.object(module, 'restore') as restore:
                with self.assertRaisesRegex(RuntimeError, error):
                    module.install(self.app, requested, self.root / '.local' / requested['id'])
                confirm.assert_not_called()
                restore.assert_not_called()

    def test_framework_diff_survives_resigning_update_and_restore(self):
        binary = self.app / self.profile['framework_binary']
        original = b'----abcd----' + bytes(range(256)) * 2048
        binary.write_bytes(original)
        self.profile['original_sha256'] = module.digest(binary)
        signature_byte = [1]

        def sign_framework(*args):
            target = Path(args[-1])
            if '--force' in args and target.suffix == '.framework':
                framework_binary = target / binary.name
                data = bytearray(framework_binary.read_bytes())
                # Signing can change headers, signature location and file length.
                data[signature_byte[0] * module.backups.BLOCK_SIZE + 50] ^= 1
                framework_binary.write_bytes(data + bytes(signature_byte) * 100)

        with patch.object(module, 'run', side_effect=sign_framework):
            self.install()
            backup = self.local / 'original' / self.profile['framework_binary']
            self.assertFalse(backup.exists())
            self.assertLess(module.backups.diff_path(backup).stat().st_size, len(original) // 10)
            self.assertEqual(module.original_framework(self.app, self.profile, self.local), original)
            signature_byte[0] = 3
            module.update(self.app, self.state(), self.profile, self.local)
            self.assertEqual(module.original_framework(self.app, self.profile, self.local), original)
            signature_byte[0] = 5
            real_replace = module.replace_file

            def fail_main(source, target):
                if target == self.app / self.profile['executable']:
                    raise OSError('interrupted update')
                real_replace(source, target)

            with patch.object(module, 'replace_file', side_effect=fail_main), \
                    patch.object(module, 'restore', side_effect=OSError('rollback interrupted')):
                with self.assertRaises(OSError):
                    module.update(self.app, self.state(), self.profile, self.local)
            self.assertEqual(self.state()['status'], 'prepared')
            self.assertEqual(module.original_framework(self.app, self.profile, self.local), original)
            module.restore(self.app, self.state(), self.profile, self.local)
            self.assertEqual(binary.read_bytes(), original)
            self.install()
            module.restore(self.app, self.state(), self.profile, self.local)
            self.assertEqual(binary.read_bytes(), original)

    def test_damaged_framework_diff_is_rejected_before_restore(self):
        self.install()
        binary = self.app / self.profile['framework_binary']
        before = binary.read_bytes()
        backup = self.local / 'original' / self.profile['framework_binary']
        module.backups.diff_path(backup).write_bytes(b'damaged diff')
        with self.assertRaisesRegex(RuntimeError, 'Original backup changed'):
            module.restore(self.app, self.state(), self.profile, self.local)
        self.assertEqual(binary.read_bytes(), before)
        self.assertEqual(self.state()['status'], 'installed')

    def test_resolver_reads_the_reconstructed_original_framework(self):
        original = (self.app / self.profile['framework_binary']).read_bytes()
        self.install()
        metadata = self.app / 'Data/Managed/Metadata/global-metadata.dat'
        metadata.parent.mkdir(parents=True)
        metadata.write_bytes(b'metadata')
        contracts = self.root / 'signatures'
        contracts.mkdir()
        (contracts / (self.profile['bundle_id'] + '.json')).write_text('{}')
        resolved = copy.deepcopy(self.profile)
        resolved['resolution'] = {'contract_sha256': 'a' * 64}
        with patch.object(module, 'applied_profile', return_value=(self.profile, self.state(), self.local, 'installed')), \
                patch('signatures.resolve_profile', return_value=resolved) as resolve:
            module.resolve_app_profile(self.app, module.read_app_info(self.app), self.profile)
        self.assertEqual(resolve.call_args.args[0], original)

    def test_staging_failure_can_retry_with_saved_backup(self):
        with patch.object(module, 'stage_framework', side_effect=RuntimeError('signing failed')):
            with self.assertRaisesRegex(RuntimeError, 'signing failed'):
                self.install()
        self.assertEqual(self.state()['status'], 'restored')
        self.install()
        self.assertEqual(self.state()['status'], 'installed')

    def test_interrupted_backup_can_retry(self):
        with patch.object(module.shutil, 'copytree', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                self.install()
        self.assertFalse(self.local.exists())
        self.install()
        self.assertEqual(self.state()['status'], 'installed')

    def test_reapply_rejects_changed_backup_signatures(self):
        self.install()
        module.restore(self.app, self.state(), self.profile, self.local)
        before = self.state()
        signature = self.local / 'original/_CodeSignature/CodeResources'
        signature.write_bytes(b'damaged backup')
        with self.assertRaisesRegex(RuntimeError, 'saved original file.*has changed'):
            self.install()
        self.assertEqual(self.state(), before)
        self.assertFalse((self.app / module.LIBRARY).exists())

    def test_legacy_signature_records_can_be_upgraded(self):
        self.install()
        module.restore(self.app, self.state(), self.profile, self.local)
        state = self.state()
        state['original'] = {p: value for p, value in state['original'].items()
                             if '_CodeSignature/' not in p}
        module.save_state(state, self.local)
        self.install()
        self.assertIn('_CodeSignature/CodeResources', self.state()['original'])

    def test_legacy_partial_signature_backup_can_be_reapplied(self):
        extra = 'Frameworks/Other.framework/_CodeSignature/CodeResources'
        (self.app / extra).parent.mkdir(parents=True)
        (self.app / extra).write_bytes(b'other framework signature')
        self.install()
        module.restore(self.app, self.state(), self.profile, self.local)
        state = self.state()
        state['original'] = {p: value for p, value in state['original'].items()
                             if '_CodeSignature/' not in p}
        module.save_state(state, self.local)
        fixtures.shutil.rmtree(self.local / 'original/Frameworks/Other.framework')
        self.install()
        self.assertEqual((self.local / 'original' / extra).read_bytes(), b'other framework signature')
        self.assertEqual(self.state()['original'][extra], module.digest(self.app / extra))

    def test_legacy_reapply_accepts_only_registered_resigning_of_the_same_code(self):
        main = self.app / self.profile['executable']
        main.write_bytes(fixtures.PatchTests().signed_executable(b'old signature'))
        self.install()
        module.restore(self.app, self.state(), self.profile, self.local)
        state = self.state()
        state['original'] = {p: value for p, value in state['original'].items() if '_CodeSignature/' not in p}
        module.save_state(state, self.local)
        registry = module.bridge_registry.load(self.app, self.profile['bundle_id'], self.profile['version'], self.profile['executable'])
        staged = self.root / 'resigned.app'
        fixtures.shutil.copytree(self.app, staged)
        (staged / self.profile['executable']).write_bytes(fixtures.PatchTests().signed_executable(b'new longer signature'))
        module.bridge_registry.begin(registry, {}, staged)
        fixtures.shutil.copy2(staged / self.profile['executable'], main)
        module.bridge_registry.finish(registry, self.app)
        self.install()
        self.assertEqual(self.state()['status'], 'installed')
        self.assertEqual(self.state()['original'][self.profile['executable']], state['original'][self.profile['executable']])

    def test_restore_rejects_extra_backup_signature_and_reapply_rejects_live_changes(self):
        self.install()
        extra = self.local / 'original/_CodeSignature/extra'
        extra.write_bytes(b'independent data')
        with self.assertRaisesRegex(RuntimeError, 'backup signatures changed'):
            module.restore(self.app, self.state(), self.profile, self.local)
        extra.unlink()
        module.restore(self.app, self.state(), self.profile, self.local)
        live = self.app / '_CodeSignature/CodeResources'
        live.write_bytes(b'independent change')
        with self.assertRaisesRegex(RuntimeError, 'game signatures differ'):
            self.install()
        self.assertEqual(live.read_bytes(), b'independent change')

    def test_restore_and_update_reject_unrecorded_signature_files(self):
        self.install()
        before = module.digest(self.app / self.profile['framework_binary'])
        _, framework, _ = module.app_paths(self.profile)
        for directory in ('_CodeSignature', framework + '/_CodeSignature'):
            with self.subTest(directory=directory):
                extra = self.app / directory / 'independent-resource'
                extra.write_bytes(b'independent data')
                with self.assertRaisesRegex(RuntimeError, 'Unrecognized signature'):
                    module.restore(self.app, self.state(), self.profile, self.local)
                with self.assertRaisesRegex(RuntimeError, 'Unrecognized signature'):
                    module.update(self.app, self.state(), self.profile, self.local)
                self.assertEqual(extra.read_bytes(), b'independent data')
                self.assertEqual(module.digest(self.app / self.profile['framework_binary']), before)
                extra.unlink()

    def test_installed_status_rejects_missing_executable_permission(self):
        self.install()
        (self.app / self.profile['executable']).chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, 'cannot be run'):
            module.check_installed(self.app, self.state(), self.profile)
        (self.root / 'profiles').mkdir()
        (self.root / 'profiles' / (self.profile['id'] + '.json')).write_text('{}')
        with patch.object(module, 'select_profile', return_value=self.profile), \
                patch.object(module, 'load_profile', return_value=self.profile), \
                patch('sys.argv', ['patch.py', 'status', '--app', str(self.app)]), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            module.main()
        self.assertIn('Needs attention', out.getvalue())

    def test_signing_failure_does_not_touch_the_live_app(self):
        before = {str(path.relative_to(self.app)): module.digest(path)
                  for path in self.app.rglob('*') if path.is_file()}
        def fail_sign(*args):
            if '--force' in args and args[-1].endswith(self.app.name):
                raise RuntimeError('signing failed')
        with patch.object(module, 'run', side_effect=fail_sign):
            with self.assertRaisesRegex(RuntimeError, 'signing failed'):
                self.install()
        after = {str(path.relative_to(self.app)): module.digest(path)
                 for path in self.app.rglob('*') if path.is_file()}
        self.assertEqual(after, before)
        self.assertEqual(self.state()['status'], 'restored')

    def test_damaged_signature_backup_is_rejected_before_restore(self):
        self.install()
        backup_signature = self.local / 'original/_CodeSignature/CodeResources'
        backup_signature.unlink()
        executable = self.app / self.profile['executable']
        before = module.digest(executable)
        with self.assertRaisesRegex(RuntimeError, 'Original backup changed'):
            module.restore(self.app, self.state(), self.profile, self.local)
        self.assertEqual(module.digest(executable), before)
        self.assertTrue((self.app / '_CodeSignature/CodeResources').exists())

    def test_changed_live_signature_is_rejected(self):
        self.install()
        signature = self.app / '_CodeSignature/CodeResources'
        signature.write_bytes(b'independent change')
        with self.assertRaisesRegex(RuntimeError, 'file changed after patching'):
            module.check_installed(self.app, self.state(), self.profile)
        with self.assertRaisesRegex(RuntimeError, 'does not match a recorded'):
            module.restore(self.app, self.state(), self.profile, self.local)
        self.assertEqual(signature.read_bytes(), b'independent change')

    def resign_with_plugin(self):
        main = self.app / self.profile['executable']
        main.write_bytes(fixtures.PatchTests().signed_executable(b'original signature'))
        self.install()
        plugin = self.app / 'Frameworks/UserPlugins/Example.dylib'
        plugin.parent.mkdir()
        plugin.write_bytes(b'custom plugin')
        main.write_bytes(module.link_library(
            fixtures.PatchTests().signed_executable(b'new plugin signature, different size')))
        (self.app / '_CodeSignature/CodeResources').write_bytes(b'plugin resource seal')
        return plugin

    def test_plugin_resigning_allows_status_update_restore_and_reapply(self):
        plugin = self.resign_with_plugin()
        main = self.profile['executable']
        registry_root = module.bridge_registry._root(self.app, self.profile['bundle_id'], self.profile['version'])
        with patch.object(module.bridge_registry.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 0)) as verify:
            module.check_installed(self.app, self.state(), self.profile)
            verify.assert_called_once_with(
                ['/usr/bin/codesign', '--verify', '--strict', '--ignore-resources', str(self.app)],
                capture_output=True)
            registry = json.loads((registry_root / 'state.json').read_text())
            self.assertEqual(registry['current']['main_sha256'], module.digest(self.app / main))
            self.bridge.write_bytes(b'bridge-v2')
            module.update(self.app, self.state(), self.profile, self.local)
            module.restore(self.app, self.state(), self.profile, self.local)
            self.assertEqual(plugin.read_bytes(), b'custom plugin')
            self.assertFalse(module.has_dylib((self.app / main).read_bytes(), module.LOAD_PATH))
            self.install()
            module.check_installed(self.app, self.state(), self.profile)
        self.assertEqual(plugin.read_bytes(), b'custom plugin')

    def test_restore_after_plugin_removal_reseals_the_staged_app(self):
        plugin = self.resign_with_plugin()
        plugin.unlink()
        fixtures.shutil.rmtree(plugin.parent)
        with patch.object(module.bridge_registry.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 0)):
            module.restore(self.app, self.state(), self.profile, self.local)
        self.assertFalse(plugin.exists())
        signs = [call.args for call in module.run.call_args_list if '--force' in call.args]
        self.assertEqual(Path(signs[-1][-1]).name, self.app.name)
        self.assertNotEqual(Path(signs[-1][-1]), self.app)
        self.assertEqual(self.state()['status'], 'restored')

    def test_resigning_does_not_accept_changed_code_load_commands_or_invalid_signature(self):
        self.resign_with_plugin()
        main = self.app / self.profile['executable']
        resigned = main.read_bytes()
        registry_root = module.bridge_registry._root(self.app, self.profile['bundle_id'], self.profile['version'])
        record = (registry_root / 'state.json').read_bytes()
        changed_code = bytearray(resigned)
        changed_code[600] ^= 1
        changed_loads = module.add_dylib(bytearray(resigned), '@executable_path/unknown.dylib')
        for contents, valid_signature in ((changed_code, True), (changed_loads, True), (resigned, False)):
            with self.subTest(valid_signature=valid_signature, contents=contents[:32]):
                main.write_bytes(contents)
                with patch.object(module.bridge_registry.subprocess, 'run',
                                  return_value=subprocess.CompletedProcess([], 0 if valid_signature else 1)):
                    with self.assertRaises(RuntimeError):
                        module.restore(self.app, self.state(), self.profile, self.local)
                self.assertEqual(main.read_bytes(), contents)
                self.assertEqual((registry_root / 'state.json').read_bytes(), record)
                self.assertEqual(self.state()['status'], 'installed')

    def test_partial_restore_can_resume_but_rejects_unrelated_changes(self):
        self.install()
        real_replace = module.replace_file
        def fail_main(source, target):
            if target == self.app / self.profile['executable']:
                raise OSError('write failed')
            real_replace(source, target)
        with patch.object(module, 'replace_file', side_effect=fail_main):
            with self.assertRaises(OSError):
                module.restore(self.app, self.state(), self.profile, self.local)
        self.assertEqual(self.state()['status'], 'restoring')
        main = self.app / self.profile['executable']
        saved = main.read_bytes()
        main.write_bytes(b'unrelated change')
        with self.assertRaisesRegex(RuntimeError, 'does not match a recorded'):
            module.restore(self.app, self.state(), self.profile, self.local)
        self.assertEqual(main.read_bytes(), b'unrelated change')
        main.write_bytes(saved)
        module.restore(self.app, self.state(), self.profile, self.local)
        self.assertEqual(self.state()['status'], 'restored')

    def test_interrupted_install_can_restore_planned_files(self):
        real_replace = module.replace_file
        def fail_main(source, target):
            if target == self.app / self.profile['executable']:
                raise OSError('interrupted')
            real_replace(source, target)
        with patch.object(module, 'replace_file', side_effect=fail_main), \
                patch.object(module, 'restore', side_effect=OSError('rollback interrupted')):
            with self.assertRaises(OSError):
                self.install()
        self.assertEqual(self.state()['status'], 'prepared')
        module.restore(self.app, self.state(), self.profile, self.local)
        self.assertEqual(self.state()['status'], 'restored')

    def test_legacy_backup_for_other_profile_is_skipped(self):
        legacy = self.root / '.local'
        legacy.mkdir()
        (legacy / 'state.json').write_text(json.dumps({
            'profile': self.profile['id'],
            'original': {self.profile['framework_binary']: load_profile()['original_sha256']},
        }))
        target = load_profile('zzz-test')
        self.assertEqual(module.local_directory(target), legacy / target['id'])

    def test_update_signing_failure_keeps_the_current_install(self):
        self.install()
        self.bridge.write_bytes(b'bridge-v2')
        def fail_sign(*args):
            if '--force' in args and args[-1].endswith(self.app.name):
                raise RuntimeError('signing interrupted')
        before = {str(path.relative_to(self.app)): module.digest(path)
                  for path in self.app.rglob('*') if path.is_file()}
        with patch.object(module, 'run', side_effect=fail_sign):
            with self.assertRaisesRegex(RuntimeError, 'signing interrupted'):
                module.update(self.app, self.state(), self.profile, self.local)
        after = {str(path.relative_to(self.app)): module.digest(path)
                 for path in self.app.rglob('*') if path.is_file()}
        self.assertEqual(after, before)
        self.assertEqual(self.state()['status'], 'installed')

    def test_cli_allows_restore_of_prepared_operation(self):
        state = {'status': 'prepared'}
        with patch.object(module, 'select_profile', return_value=self.profile), \
                patch.object(module, 'applied_profile', return_value=(self.profile, state, self.local, 'prepared')), \
                patch.object(module, 'restore') as restore, \
                patch('sys.argv', ['patch.py', 'restore', '--app', str(self.app)]):
            module.main()
        restore.assert_called_once_with(self.app, state, self.profile, self.local)

    def test_modified_saved_main_is_not_reported_unpatched(self):
        self.install()
        module.restore(self.app, self.state(), self.profile, self.local)
        (self.app / self.profile['executable']).write_bytes(b'modified executable')
        with patch.object(module, 'select_profile', return_value=self.profile), \
                patch('sys.argv', ['patch.py', 'status', '--app', str(self.app)]):
            with self.assertRaisesRegex(RuntimeError, 'differs from its saved original'):
                module.main()

    def test_missing_main_is_not_reported_unpatched(self):
        (self.app / self.profile['executable']).unlink()
        with patch.object(module, 'select_profile', return_value=self.profile), \
                patch('sys.argv', ['patch.py', 'status', '--app', str(self.app)]):
            with self.assertRaisesRegex(RuntimeError, 'executable is missing'):
                module.main()

    def test_bad_evidence_path_is_rejected(self):
        profile = copy.deepcopy(load_profile())
        profile['validation']['evidence'] = 'docs/missing.md'
        with self.assertRaisesRegex(RuntimeError, 'evidence'):
            validate(profile, profile['id'])


class ProcessCheckTests(unittest.TestCase):
    def test_process_errors_are_distinct_from_running_game(self):
        with patch.object(module.subprocess, 'run') as run:
            run.return_value = subprocess.CompletedProcess([], 3, b'', b'process service unavailable')
            with self.assertRaisesRegex(RuntimeError, 'Could not check.*process service unavailable'):
                module.closed(load_profile())
            run.return_value = subprocess.CompletedProcess([], 0, b'123', b'')
            with self.assertRaisesRegex(RuntimeError, 'Quit'):
                module.closed(load_profile())
            run.return_value = subprocess.CompletedProcess([], 1, b'', b'')
            module.closed(load_profile())

    def test_long_executable_name_matches_basename(self):
        profile = dict(load_profile(), executable='ZenlessZoneZeroBeta')
        with patch.object(module.subprocess, 'run') as run:
            run.side_effect = [
                subprocess.CompletedProcess([], 0, b'101 102\n', b''),
                subprocess.CompletedProcess([], 0, b'/Applications/Other.app/ZenlessZoneZeroOther\n', b''),
            ]
            module.closed(profile)
            self.assertEqual(run.call_args_list[0].args[0], ['/usr/bin/pgrep', '-x', 'ZenlessZoneZero'])
            self.assertEqual(run.call_args_list[1].args[0], ['/bin/ps', '-p', '101,102', '-o', 'comm='])

            run.reset_mock()
            run.side_effect = [
                subprocess.CompletedProcess([], 0, b'205\n', b''),
                subprocess.CompletedProcess([], 0, b'/Applications/ZZZ.app/ZenlessZoneZeroBeta\n', b''),
            ]
            with self.assertRaisesRegex(RuntimeError, 'Quit'):
                module.closed(profile)
