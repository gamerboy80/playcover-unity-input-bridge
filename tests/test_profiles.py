import copy
from pathlib import Path
import unittest

from profiles import ROOT, generate_header, load_profile, validate


class ProfileTests(unittest.TestCase):
    def test_all_profiles_validate_and_generate_named_constants(self):
        for path in (ROOT / 'profiles').glob('*.json'):
            with self.subTest(profile=path.stem):
                profile = load_profile(path.stem)
                header = generate_header(profile)
                self.assertIn('#define GameProfileID "' + path.stem + '"', header)
                self.assertIn('#define GameMouseMakeCurrent ', header)
                self.assertIn('#define GameFieldMouseScroll ', header)
                self.assertEqual(header, generate_header(profile))

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
