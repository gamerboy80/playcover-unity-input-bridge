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

    def test_staging_failure_can_retry_with_saved_backup(self):
        with patch.object(module, 'stage_framework', side_effect=RuntimeError('signing failed')):
            with self.assertRaisesRegex(RuntimeError, 'signing failed'):
                self.install()
        self.assertEqual(self.state()['status'], 'restored')
        self.install()
        self.assertEqual(self.state()['status'], 'installed')

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
