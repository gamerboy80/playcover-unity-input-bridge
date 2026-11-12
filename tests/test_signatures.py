import json
import os
from pathlib import Path
import struct
import unittest

from profiles import ROOT, load_profile
from signatures import Image, Metadata, decode, resolve_functions, resolve_profile, scan, unique


def uleb(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return result


def fixture_image(field=0x154):
    data = bytearray(8192)
    struct.pack_into('<6I', data, 0, 0xfeedfacf, 0x100000c, 0, 6, 3, 240)
    struct.pack_into('<II16s4Q4I', data, 32, 0x19, 152, b'__TEXT',
                     0x10000000, 4096, 0, 4096, 7, 5, 1, 0)
    struct.pack_into('<16s16sQQI', data, 104, b'__text', b'__TEXT', 0x10000200, 256, 512)
    struct.pack_into('<II16s4Q4I', data, 184, 0x19, 72, b'__DATA',
                     0x20000000, 8192, 4096, 4096, 3, 3, 0, 0)
    deltas = uleb(512) + uleb(32) + uleb(32) + uleb(64) + b'\0'
    struct.pack_into('<4I', data, 256, 0x26, 16, 0x1800, len(deltas))
    data[0x1800:0x1800 + len(deltas)] = deltas
    struct.pack_into('<II', data, 0x220, 0xb9400000 | (field // 4) << 10, 0xd65f03c0)
    struct.pack_into('<II', data, 0x240, 0x52800020, 0xd65f03c0)
    data[0x800:0x80a] = b'\0Test.dll\0'
    struct.pack_into('<Q', data, 0x1100, 0x10000801)
    struct.pack_into('<Q', data, 0x1100 - 24, 0x20000200)
    struct.pack_into('<QQ', data, 0x1200 + 16, 0x10000220, 0x10000240)
    return data


def fixture_metadata():
    data = bytearray(65536)
    pool = bytearray(b'mscorlib\0\0mscorlib.dll\0<Module>\0Locale\0.ctor\0msg\0GetText\0fmt\0args\0')
    def string(value):
        index = len(pool)
        pool.extend(value.encode() + b'\0')
        return index
    foo, bar = string('Foo'), string('Bar')
    for index in range(105):
        row = [0] * 20
        row[1] = 0 if index == 1 else 3 if index == 2 else 0xffffffff
        row[2] = 9
        row[5] = 0x02000001 + index
        row[10] = 23 if index == 0 else 32 if index == 1 else string('Class' + str(index))
        struct.pack_into('<20I', data, 0x2000 + index * 80, *row)
    data[0x1000:0x1000 + len(pool)] = pool
    for index, (declaring, name, parameters) in enumerate([(1, 39, 0), (1, 49, 1), (1, 49, 2), (2, foo, 0), (2, bar, 0)]):
        pos = 0x5000 + index * 30
        struct.pack_into('<II', data, pos, declaring, name)
        struct.pack_into('<HI', data, pos + 20, parameters, 0x06000001 + index)
    return data


class SignatureTests(unittest.TestCase):
    def rules(self):
        base = {'namespace': '', 'class': 'Class2', 'module': 'Test.dll', 'parameters': 0}
        return {
            'Foo': dict(base, method='Foo', pattern='000040b9c0035fd6', mask='ff03c0ffffffffff'),
            'Bar': dict(base, method='Bar', pattern='20008052c0035fd6'),
        }

    def test_metadata_and_signatures_resolve_relocated_methods_and_changed_fields(self):
        metadata = Metadata(fixture_metadata())
        for field in (0x154, 0x1c0):
            with self.subTest(field=field):
                image = Image(fixture_image(field))
                functions = resolve_functions(image, metadata, self.rules())
                self.assertEqual(functions, {'Foo': 0x10000220, 'Bar': 0x10000240})
                self.assertEqual(decode(image, functions['Foo'], 'load'), field)
                self.assertEqual(image.file(0x20000200), 0x1200)
                with self.assertRaisesRegex(RuntimeError, 'file-backed'):
                    image.file(0x20001000)

    def test_wrong_code_missing_method_and_ambiguous_metadata_are_rejected(self):
        metadata = Metadata(fixture_metadata())
        rules = self.rules()
        rules['Bar']['pattern'] = '40008052c0035fd6'
        with self.assertRaisesRegex(RuntimeError, 'verified match, found 0'):
            resolve_functions(Image(fixture_image()), metadata, rules)
        rules = self.rules()
        rules['Foo']['parameters'] = 3
        with self.assertRaisesRegex(RuntimeError, 'Foo.*found 0'):
            resolve_functions(Image(fixture_image()), metadata, rules)
        data = fixture_metadata()
        data[0x6000:0x6000 + 90] = data[0x5000:0x5000 + 90]
        with self.assertRaisesRegex(RuntimeError, 'method records.*found 2'):
            Metadata(data)

    def test_reports_all_missing_native_function_signatures(self):
        absent = {'pattern': 'f0f0f0f0f0f0f0f0'}
        with self.assertRaises(RuntimeError) as raised:
            resolve_functions(Image(fixture_image()), None,
                              {'FirstMissing': absent, 'SecondMissing': absent})
        message = str(raised.exception)
        self.assertIn('FirstMissing: expected one verified match, found 0', message)
        self.assertIn('SecondMissing: expected one verified match, found 0', message)

    def test_scanner_rejects_ambiguity_alignment_and_overrun(self):
        pattern = bytes.fromhex('20008052c0035fd6')
        mask = b'\xff' * len(pattern)
        data = pattern + pattern + b'x' + pattern
        self.assertEqual(list(scan(data, pattern, mask)), [0, 8])
        with self.assertRaisesRegex(RuntimeError, 'found 2'):
            unique(scan(data, pattern, mask), 'ambiguous')
        self.assertEqual(list(scan(data, pattern, mask, end=7)), [])
        with self.assertRaisesRegex(RuntimeError, 'fixed bytes'):
            list(scan(data, pattern, bytes(len(pattern))))

    def test_register_chain_must_match_and_negative_adrp_is_sign_extended(self):
        data = fixture_image()
        # ADRP x8 to the previous page, ADD x8,x8,#0x28.
        struct.pack_into('<4I', data, 0x220, 0xf0ffffe8, 0x9100a108, 0xf9400100, 0xd65f03c0)
        image = Image(data)
        self.assertEqual(decode(image, 0x10000220, 'adrp-add'), 0xffff028)
        struct.pack_into('<I', data, 0x224, 0x9100a128)  # ADD x8,x9,#0x28.
        with self.assertRaisesRegex(RuntimeError, 'register chain'):
            decode(Image(data), 0x10000220, 'adrp-add')

    def test_native_contract_decodes_slots_return_sites_and_relocated_calls(self):
        data = fixture_image()
        struct.pack_into('<4I', data, 0x220, 0x90080008, 0x91000108, 0xf9401101, 0xd61f0020)
        struct.pack_into('<3I', data, 0x240, 0xd63f0100, 0x94000000, 0xd65f03c0)
        profile = load_profile('hsr')
        profile['patches'] = [dict(name='redirect', reason='Synthetic call', file_offset='0x244',
                                   expected='00000094', replacement='00000094')]
        contract = dict(schema_version=1, id='synthetic-native', metadata='none',
                        bundle_id=profile['bundle_id'],
                        functions={'Getter': {'pattern': data[0x220:0x230].hex()},
                                   'Caller': {'pattern': data[0x240:0x24c].hex()}},
                        extract={'Slot': dict(function='Getter', pattern=data[0x220:0x230].hex(),
                                              kind='adrp-add-load', alignment=8),
                                 'Return': dict(function='Caller', pattern=data[0x240:0x248].hex(),
                                                offset=4, kind='return-pc')}, equal=[], fields={},
                        addresses={name: 'Slot' if name.endswith('Slot') else 'Return' if name.endswith('Return')
                                   else 'Caller' for name in profile['bridge']['addresses']},
                        patches={'redirect': dict(function='Caller', pattern=data[0x240:0x24c].hex(),
                                                  offset=4, expected='00000094', replacement='00000094',
                                                  call_to='Getter')})
        result = resolve_profile(data, b'', profile, contract, '4.6.0')
        self.assertEqual(result['bridge']['addresses']['KeySlot'], '0x20000020')
        self.assertEqual(result['bridge']['addresses']['UIScrollReturn'], '0x10000244')
        self.assertNotIn('ReadVector2', result['bridge']['addresses'])
        self.assertEqual(result['patches'][0]['replacement'], 'f7ffff97')
        contract['addresses']['KeySlot'] = 'Return'
        with self.assertRaisesRegex(RuntimeError, 'outside writable data'):
            resolve_profile(data, b'', profile, contract, '4.6.0')
        contract['addresses']['KeySlot'] = 'Slot'
        # A return address must follow BLR.
        struct.pack_into('<I', data, 0x240, 0xd65f03c0)
        with self.assertRaisesRegex(RuntimeError, 'Expected BLR'):
            decode(Image(data), 0x10000244, 'return-pc')

    @unittest.skipUnless(os.environ.get('HSR_ORIGINAL_FRAMEWORK'), 'Optional local HSR fixture')
    def test_hsr_binary_reconstructs_regular_and_test_profiles(self):
        binary = Path(os.environ['HSR_ORIGINAL_FRAMEWORK']).read_bytes()
        contract = json.loads((ROOT / 'signatures/com.HoYoverse.hkrpgoversea.json').read_text())
        for suffix in ('', '-platform-pc-settings-test'):
            expected = load_profile('com.HoYoverse.hkrpgoversea-4.6.0' + suffix)
            result = resolve_profile(binary, b'', expected, contract, expected['version'])
            self.assertEqual(result['bridge'], expected['bridge'])
            self.assertEqual(result['patches'], expected['patches'])
            self.assertEqual(result['original_sha256'], expected['original_sha256'])

    @unittest.skipUnless(os.environ.get('HSR_47_APP'), 'Optional local HSR 4.7.0 fixture')
    def test_hsr_managed_names_reconstruct_both_47_profiles(self):
        app = Path(os.environ['HSR_47_APP'])
        contract = json.loads((ROOT / 'signatures/com.HoYoverse.hkrpgoversea.json').read_text())
        metadata = (app / 'Data/Managed/Metadata/global-metadata.dat').read_bytes()
        binary = (app / load_profile('hsr')['framework_binary']).read_bytes()
        for suffix in ('', '-platform-pc-settings-test'):
            expected = load_profile('com.HoYoverse.hkrpgoversea-4.7.0' + suffix)
            result = resolve_profile(binary, metadata, expected, contract, expected['version'])
            self.assertEqual(result['bridge'], expected['bridge'])
            self.assertEqual(result['patches'], expected['patches'])
            self.assertEqual(result['original_sha256'], expected['original_sha256'])

    @unittest.skipUnless(os.environ.get('ZZZ_ORIGINAL_FRAMEWORK'), 'Optional local game fixture')
    def test_local_binary_reconstructs_both_reviewed_profiles(self):
        binary = Path(os.environ['ZZZ_ORIGINAL_FRAMEWORK']).read_bytes()
        metadata = Path(os.environ['ZZZ_METADATA']).read_bytes()
        contract = json.loads((ROOT / 'signatures/com.HoYoverse.Nap.json').read_text())
        for alias in ('zzz', 'zzz-test'):
            expected = load_profile(alias)
            result = resolve_profile(binary, metadata, expected, contract, '3.3.1')
            self.assertEqual(result['bridge'], expected['bridge'])
            self.assertEqual(result['patches'], expected['patches'])
            self.assertEqual(result['original_sha256'], expected['original_sha256'])
