"""Discovery and detour guards use synthetic Mach-O files, with optional real-game checks."""
import copy
import hashlib
import json
import os
import plistlib
import shutil
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from plugins.signature_resolver import resolve, resolve_app
from signatures import HsrMethods, Image
from test_signatures import fixture_image
from plugins.veritas import stage as hsr
from plugins.zzz_damage import stage as zzz
import test_zzz_damage


class PluginSignatureTests(unittest.TestCase):
    def fixture(self):
        data, profile = test_zzz_damage.DamageProbeTests().image()
        profile['bundle_id'] = 'test.game'
        contract = {'bundle_id': 'test.game', 'metadata': 'none',
                    'functions': {'Test': {'pattern': profile['entries']['Test']['expected']}},
                    'bindings': {'Test': ['entry', 'Test']}}
        return data, profile, contract

    def test_native_discovery_and_exact_abi_cross_check(self):
        data, profile, contract = self.fixture()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'signatures.json'
            path.write_text(json.dumps(contract))
            resolved, evidence = resolve(data, profile, path)
            self.assertEqual(resolved, profile)
            self.assertEqual(evidence['functions'], {'Test': '0x220'})
            changed = copy.deepcopy(profile)
            changed['entries']['Test']['address'] = '0x230'
            with self.assertRaisesRegex(RuntimeError, 'Discovered bindings differ'):
                resolve(data, changed, path)
            with self.assertRaisesRegex(RuntimeError, 'hash'):
                resolve(data + b'x', profile, path)

    def test_missing_ambiguous_and_incomplete_bindings_stop_resolution(self):
        data, profile, contract = self.fixture()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'signatures.json'
            for mode in ['missing', 'ambiguous', 'incomplete']:
                modified, spec = bytearray(data), copy.deepcopy(contract)
                if mode == 'missing': spec['functions']['Test']['pattern'] = 'deadbeef'
                if mode == 'ambiguous': modified[0x240:0x24c] = modified[0x220:0x22c]
                if mode == 'incomplete': spec['bindings'] = {}
                p = copy.deepcopy(profile); p['framework_sha256'] = [hashlib.sha256(modified).hexdigest()]
                path.write_text(json.dumps(spec))
                with self.subTest(mode=mode), self.assertRaises(RuntimeError): resolve(modified, p, path)

    def test_hsr_detours_preserve_all_other_bytes_and_reject_unsafe_prologues(self):
        data, profile, _ = self.fixture()
        profile['entries'] = {name: [entry['address'], entry['expected']] for name, entry in profile['entries'].items()}
        patched = hsr.instrument(data, profile)
        for _, entry, expected, jump, stub, _, _, code in hsr.detours(profile):
            self.assertEqual(patched[entry:entry + 12], jump)
            self.assertEqual(patched[stub:stub + len(code)], code)
            self.assertEqual(code[20:32], expected)
            patched[entry:entry + 12] = data[entry:entry + 12]
            patched[stub:stub + len(code)] = data[stub:stub + len(code)]
        self.assertEqual(patched, data)
        for op in [0x94000001, 0x90000000, 0x58000000, 0xd61f0200]:
            with self.assertRaisesRegex(RuntimeError, 'relocatable'):
                hsr.validate_prologue(struct.pack('<I', op) + bytes.fromhex('fd7b01a9fd430091'))
        for mutation, message in [('padding', 'padding'), ('slot', 'zero-filled'), ('overlap', 'Overlapping')]:
            changed, p = bytearray(data), copy.deepcopy(profile)
            if mutation == 'padding': changed[0x900] = 1
            if mutation == 'slot': p['data_padding'] = '0x20000000'
            if mutation == 'overlap': p['entries']['Other'] = p['entries']['Test'][:]
            p['framework_sha256'] = [hashlib.sha256(changed).hexdigest()]
            with self.subTest(mutation=mutation), self.assertRaisesRegex(RuntimeError, message): hsr.instrument(changed, p)

    def test_hsr_staging_records_plan_before_copy_and_preserves_source_on_failure(self):
        for mode in ['success', 'signing_failure', 'source_changed']:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                app, output = root / 'source.app', root / 'preview.app'
                app.mkdir()
                data, profile, _ = self.fixture()
                profile['entries'] = {key: [entry['address'], entry['expected']] for key, entry in profile['entries'].items()}
                profile.update(bundle_id='test.game', version='1', executable='Game')
                (app / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'test.game',
                    'CFBundleShortVersionString': '1', 'CFBundleExecutable': 'Game'}))
                (app / 'Game').write_bytes(b'game')
                source = app / hsr.FRAMEWORK / 'UnityFramework'
                source.parent.mkdir(parents=True); source.write_bytes(data)
                plugin = root / 'build/plugins/VeritasLive.dylib'
                plugin.parent.mkdir(parents=True); plugin.write_bytes(b'plugin')
                evidence = {'framework_sha256': hashlib.sha256(data).hexdigest(), 'contract_sha256': '0' * 64}

                def clone(original, staged):
                    record = json.loads(output.with_suffix('.plan.json').read_text())
                    self.assertEqual(record['source_framework_sha256'], evidence['framework_sha256'])
                    self.assertEqual(record['planned_unsigned_framework_sha256'], hashlib.sha256(hsr.instrument(data, profile)).hexdigest())
                    shutil.copytree(original, staged)
                    if mode == 'source_changed': source.write_bytes(data + b'external change')

                def sign(*_):
                    if mode == 'signing_failure': raise RuntimeError('signing failed')

                with patch.object(hsr, 'ROOT', root), patch.object(hsr, 'PROFILE', profile), \
                        patch.object(hsr, 'closed'), patch.object(hsr, 'resolve_app', return_value=(profile, evidence)), \
                        patch.object(hsr, 'save_evidence', return_value=Path('.local/profiles/test.json')), \
                        patch.object(hsr, 'clone_app', side_effect=clone), patch.object(hsr, 'run', side_effect=sign):
                    if mode == 'success':
                        hsr.stage(app, output)
                        self.assertEqual((output / hsr.FRAMEWORK / 'UnityFramework').read_bytes(), hsr.instrument(data, profile))
                    else:
                        with self.assertRaises(RuntimeError): hsr.stage(app, output)
                        self.assertFalse(output.exists())
                    self.assertEqual(source.read_bytes(), data + (b'external change' if mode == 'source_changed' else b''))
                    self.assertEqual((app / 'Game').read_bytes(), b'game')

    def test_contracts_cover_every_callable_and_named_zzz_hook(self):
        for module in [hsr, zzz]:
            contract = json.loads(module.CONTRACT.read_text())
            bindings = {tuple(binding) for binding in contract['bindings'].values()}
            self.assertTrue({('entry', key) for key in module.PROFILE['entries']} <= bindings)
            self.assertTrue({('method', key) for key in module.PROFILE.get('methods', {})} <= bindings)
        contract = json.loads(zzz.CONTRACT.read_text())
        for name in zzz.PROFILE['entries']:
            self.assertIn('method', contract['functions'][name])
            self.assertIn('registration_anchor', contract['functions'][name])
        self.assertEqual(hsr.PROFILE['properties']['CurrentHP'], 10)
        self.assertEqual(hsr.PROFILE['properties']['MaxHP'], 1)

    def test_managed_overloads_and_duplicate_class_names_need_independent_evidence(self):
        methods = object.__new__(HsrMethods)
        methods.image = Image(fixture_image())
        methods.index = {('Texture', 'Read'): [0x10000220, 0x10000240]}
        with self.assertRaisesRegex(RuntimeError, 'found 2'):
            methods.address({'class': 'Texture', 'method': 'Read'})
        result = methods.address({'class': 'Texture', 'method': 'Read',
                                  'verify': {'pattern': '20008052c0035fd6'}})
        self.assertEqual(result, 0x10000240)
        methods.classes = {'Sprite': [7, 8]}
        methods.class_methods = {7: {'get_texture': [0x10000220]}, 8: {'get_texture': [0x10000240]}}
        with self.assertRaisesRegex(RuntimeError, 'found 2'):
            methods.type_index({'class': 'Sprite'}, {})
        self.assertEqual(methods.type_index({'class': 'Sprite', 'method': 'get_texture', 'function': 'Texture'},
                                           {'Texture': result}), 8)

    def test_header_generation_does_not_need_proprietary_fixtures(self):
        with tempfile.TemporaryDirectory() as temporary:
            for module in [hsr, zzz]:
                path = Path(temporary) / (module.__name__ + '.h')
                module.write_header(path)
                self.assertTrue(path.stat().st_size > 1000)

    @unittest.skipUnless(os.environ.get('PLUGIN_GAME_FIXTURES'), 'Optional local plugin fixtures')
    def test_reviewed_installed_games_resolve_all_targets(self):
        base = Path.home() / 'Library/Containers/io.playcover.PlayCover/Applications'
        for module in [hsr, zzz]:
            result, evidence = resolve_app(base / (module.PROFILE['bundle_id'] + '.app'), module.PROFILE, module.CONTRACT)
            self.assertEqual(result['entries'], module.PROFILE['entries'])
            self.assertEqual(set(evidence['functions']), set(json.loads(module.CONTRACT.read_text())['functions']))
