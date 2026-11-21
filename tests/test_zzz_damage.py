import copy
import hashlib
import json
from pathlib import Path
import plistlib
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch

from plugins.zzz_damage import report, stage
from test_signatures import fixture_image


class DamageProbeTests(unittest.TestCase):
    def image(self):
        data = fixture_image()
        # Move only the synthetic __TEXT VM base to zero, retaining distinct DATA mappings.
        struct.pack_into('<Q', data, 56, 0)
        struct.pack_into('<Q', data, 136, 512)
        # Add a UUID load command in unused header space.
        struct.pack_into('<II', data, 16, 4, 264)
        struct.pack_into('<II16s', data, 272, 0x1b, 24, bytes(16))
        data[0x220:0x22c] = bytes.fromhex('f44fbea9fd7b01a9fd430091')
        profile = {'framework_sha256': [hashlib.sha256(data).hexdigest()], 'uuid': bytes(16).hex(),
                   'code_padding': '0x900', 'data_padding': '0x20001000',
                   'entries': {'Test': {'address': '0x220', 'expected': data[0x220:0x22c].hex()}}}
        profile['entries']['Test']['replacement'] = (
            stage.address_in_x16(0x220, 0x900) + stage.words(0xd61f0200)).hex()
        return data, profile

    def test_instrument_preserves_all_other_bytes_and_uses_vm_mapping(self):
        data, profile = self.image()
        patched = stage.instrument(data, profile)
        detour = next(stage.detours(profile))
        _, entry, expected, jump, stub, slot, code = detour
        self.assertEqual(patched[entry:entry + 12], jump)
        self.assertEqual(patched[stub:stub + len(code)], code)
        self.assertEqual(code[20:32], expected)
        self.assertEqual(slot, 0x20001000)
        for start, replacement in [(entry, jump), (stub, code)]:
            patched[start:start + len(replacement)] = data[start:start + len(replacement)]
        self.assertEqual(patched, data)

    def test_rejects_unknown_hash_changed_entry_used_padding_and_overlaps(self):
        data, profile = self.image()
        with self.assertRaisesRegex(RuntimeError, 'hash'):
            stage.instrument(data + b'x', profile)
        profile['avatar_getters'] = {'AvatarName': {'address': '0x220', 'expected': '00000000'}}
        with self.assertRaisesRegex(RuntimeError, 'AvatarName getter changed'):
            stage.instrument(data, profile)
        del profile['avatar_getters']
        for mutation, message in [('entry', 'entry changed'), ('padding', 'padding is in use'),
                                  ('overlap', 'Overlapping'), ('slot', 'zero-filled'), ('alignment', 'Unaligned')]:
            changed, p = bytearray(data), copy.deepcopy(profile)
            if mutation == 'entry': changed[0x220] ^= 1
            if mutation == 'padding': changed[0x900] = 1
            if mutation == 'overlap': p['entries']['Other'] = p['entries']['Test'].copy()
            if mutation == 'overlap':
                p['entries']['Other']['replacement'] = (
                    stage.address_in_x16(0x220, 0x930) + stage.words(0xd61f0200)).hex()
            if mutation == 'slot': p['data_padding'] = '0x20000000'
            if mutation == 'alignment': p['code_padding'] = '0x901'
            p['framework_sha256'] = [hashlib.sha256(changed).hexdigest()]
            with self.subTest(mutation=mutation), self.assertRaisesRegex(RuntimeError, message):
                stage.instrument(changed, p)

    def test_staging_records_plan_and_preserves_source_on_success_or_signing_failure(self):
        for fail in [False, True]:
            with self.subTest(signing_failure=fail), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                app, output = root / 'source.app', root / 'preview.app'
                app.mkdir()
                data, profile = self.image()
                profile.update(bundle_id='test.game', version='1', build='4', executable='Game', game='Test')
                (app / 'Info.plist').write_bytes(plistlib.dumps({
                    'CFBundleIdentifier': 'test.game', 'CFBundleShortVersionString': '1',
                    'CFBundleVersion': '4', 'CFBundleExecutable': 'Game'}))
                (app / 'Game').write_bytes(b'original executable')
                source = app / stage.FRAMEWORK / 'UnityFramework'
                source.parent.mkdir(parents=True)
                source.write_bytes(data)
                metadata = app / 'Data/Managed/Metadata/global-metadata.dat'
                metadata.parent.mkdir(parents=True)
                metadata.write_bytes(b'metadata')
                profile['metadata_sha256'] = stage.digest(metadata)
                plugin = root / 'build/plugins' / stage.PLUGIN
                plugin.parent.mkdir(parents=True)
                plugin.write_bytes(b'plugin')
                instrument = stage.instrument

                def sign(*args):
                    self.assertEqual(source.read_bytes(), data)
                    plan = json.loads(output.with_suffix('.plan.json').read_text())
                    self.assertEqual(plan['source_framework_sha256'], hashlib.sha256(data).hexdigest())
                    if fail:
                        raise RuntimeError('synthetic signing failure')

                with patch.object(stage, 'ROOT', root), patch.object(stage, 'PROFILE', profile), \
                        patch.object(stage, 'closed'), patch.object(stage, 'clone_app', side_effect=shutil.copytree), \
                        patch.object(stage, 'instrument', side_effect=lambda b: instrument(b, profile)), \
                        patch.object(stage, 'run', side_effect=sign):
                    if fail:
                        with self.assertRaisesRegex(RuntimeError, 'signing failure'):
                            stage.stage(app, output)
                        self.assertFalse(output.exists())
                    else:
                        stage.stage(app, output)
                        self.assertEqual((output / 'Game').read_bytes(), b'original executable')
                        self.assertEqual((output / stage.FRAMEWORK / 'UnityFramework').read_bytes(),
                                         instrument(data, profile))
                    self.assertEqual(source.read_bytes(), data)

    def capture(self):
        records = [{'type': 'session', 'schema': 1}, {'type': 'hooks', 'ready': True}]
        for phase, source in [(1, 100), (2, 200), (3, 100)]:
            records.append({'type': 'marker', 'phase': phase})
            for _ in range(3):
                records.append({'type': 'damage_candidate', 'sequence': len(records), 'phase': phase,
                                'amount': 1234.5, 'source_id': source, 'target_id': 300,
                                'source_lookup': {'observed': True, 'matches': True, 'id': source},
                                'target_lookup': {'observed': True, 'matches': True, 'id': 300}})
        return records

    def test_controlled_sources_and_independent_amount_checks(self):
        capture = self.capture()
        result = report.summarize(capture, {3: 1235, 4: 999, 999: 1})
        self.assertEqual(result['attribution_check'], 'consistent')
        self.assertFalse(result['coverage_verified'])
        self.assertEqual([c['matches_display_rounding'] for c in result['amount_checks']], [True, False, False])

    def test_current_agent_fallback_unresolved_ids_truncation_and_missing_phases_cannot_pass(self):
        for mutation in ['wrong_source', 'unresolved', 'wrong_lookup_id', 'no_marker', 'truncated', 'few_hits']:
            capture = self.capture()
            event = capture[-1]
            if mutation == 'wrong_source': event['source_id'] = event['source_lookup']['id'] = 200
            if mutation == 'unresolved': event['source_lookup']['observed'] = False
            if mutation == 'wrong_lookup_id': event['source_lookup']['id'] = 999
            if mutation == 'no_marker': capture = [r for r in capture if r['type'] != 'marker']
            if mutation == 'truncated': capture.append({'type': 'limit'})
            if mutation == 'few_hits': capture.pop()
            with self.subTest(mutation=mutation):
                self.assertEqual(report.summarize(capture)['attribution_check'], 'inconclusive')

    def test_malformed_or_combined_captures_are_rejected(self):
        capture = self.capture()
        with self.assertRaisesRegex(ValueError, 'complete'):
            report.summarize(capture + capture)
        capture[-1]['sequence'] = capture[-2]['sequence']
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            report.summarize(capture)
        with self.assertRaisesRegex(ValueError, 'JSON objects'):
            report.summarize([[]])


if __name__ == '__main__':
    unittest.main()
