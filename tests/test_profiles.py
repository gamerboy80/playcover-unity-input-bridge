import copy
from pathlib import Path
import unittest
import json
import tempfile
from unittest.mock import patch
import profiles as module

from profiles import ROOT, generate_header, load_profile, validate, select_profile


class ProfileTests(unittest.TestCase):
    def test_all_profiles_validate_and_generate_named_constants(self):
        for path in (ROOT / 'profiles').glob('*.json'):
            with self.subTest(profile=path.stem):
                profile = load_profile(path.stem)
                header = generate_header(profile)
                self.assertIn('#define GameProfileID "' + path.stem + '"', header)
                if profile['bridge']['backend']=='unity-input-system-v1':
                    self.assertIn('#define GameMouseMakeCurrent ', header)
                    self.assertIn('#define GameFieldMouseScroll ', header)
                else:
                    self.assertIn('#define GameSetKey ', header)
                    self.assertIn('#define GameLegacyBackend 1', header)
                self.assertEqual(header, generate_header(profile))

    def test_app_selection_aliases_and_mismatches(self):
        for alias in ('hsr', 'zzz-3.3.0'):
            profile = load_profile(alias)
            self.assertEqual(profile['id'], profile['bundle_id'] + '-' + profile['version'])
            info = {'CFBundleIdentifier': profile['bundle_id'],
                    'CFBundleShortVersionString': profile['version'],
                    'CFBundleExecutable': profile['executable']}
            self.assertEqual(select_profile(info), profile)
            self.assertEqual(select_profile(info, alias), profile)
            for key in info:
                wrong = dict(info, **{key: 'unsupported'})
                with self.assertRaisesRegex(RuntimeError, 'No matching profile'):
                    select_profile(wrong)
                with self.assertRaisesRegex(RuntimeError, 'does not match'):
                    select_profile(wrong, alias)
        with tempfile.TemporaryDirectory() as tmp, patch.object(module, 'ROOT', Path(tmp)):
            directory = Path(tmp) / 'profiles'
            directory.mkdir()
            for name in ('build-a', 'build-b'):
                (directory / (name + '.json')).write_text(json.dumps(dict(profile, id=name)))
            with self.assertRaisesRegex(RuntimeError, 'Ambiguous'):
                select_profile(info)

    def test_a_new_profile_changes_generated_runtime_values(self):
        profile = copy.deepcopy(load_profile())
        profile['id'] = 'another-game-1.0'
        profile['bridge']['addresses']['NativeTime'] = '0x123400'
        profile['bridge']['addresses']['EnableMouseProcessing'] = '0x0'
        header = generate_header(validate(profile, profile['id']))
        self.assertIn('#define GameNativeTime 0x123400ULL', header)
        self.assertIn('#define GameEnableMouseProcessing 0x0ULL', header)

    def test_optional_mouse_callbacks_default_off_and_require_pointer_alignment(self):
        profile = copy.deepcopy(load_profile())
        from profiles import OPTIONAL_ADDRESSES
        for key in OPTIONAL_ADDRESSES:
            profile['bridge']['addresses'].pop(key, None)
        header = generate_header(validate(profile, profile['id']))
        self.assertIn('#define GameLegacyMousePresentSlot 0x0ULL', header)
        profile['bridge']['addresses']['LegacyMousePresentSlot'] = '0x1004'
        with self.assertRaisesRegex(RuntimeError, 'callback slot'):
            validate(profile, profile['id'])

    def test_rejects_unknown_backend_paths_missing_addresses_and_unsafe_patches(self):
        original = load_profile()
        mutations = [
            lambda p: p.update(schema_version=2),
            lambda p: p.update(framework_binary='../UnityFramework'),
            lambda p: p['bridge'].update(backend='guessed-engine'),
            lambda p: p['bridge']['addresses'].pop('NativeTime'),
            lambda p: p['bridge']['addresses'].update(NativeTime='0x3'),
            lambda p: p['bridge'].update(mouse_state_bytes=65),
            lambda p: p['patches'][0].update(replacement='ff'),
            lambda p: p['patches'].append(dict(p['patches'][0], name='overlaps')),
        ]
        for mutate in mutations:
            profile = copy.deepcopy(original)
            mutate(profile)
            with self.subTest(profile=profile), self.assertRaises(RuntimeError):
                validate(profile, original['id'])
        with self.assertRaisesRegex(RuntimeError, 'profile ID'):
            load_profile('../escape')


if __name__ == '__main__':
    unittest.main()
