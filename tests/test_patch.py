import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('zzz_patch', ROOT / 'patch.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PatchTests(unittest.TestCase):
    def test_instruction_changes_are_exact_and_reject_wrong_bytes(self):
        with patch.object(module, 'PATCHES', ((4, b'abcd', b'WXYZ'), (20, b'efgh', b'1234'))):
            source = bytearray(b'----abcd------------efgh----')
            result = module.patch_instructions(source.copy())
            self.assertEqual(result, b'----WXYZ------------1234----')
            source[4] = 0
            with self.assertRaisesRegex(RuntimeError, 'Unexpected instructions'):
                module.patch_instructions(source)

    def executable(self):
        binary = bytearray(1024)
        struct.pack_into('<I', binary, 0, 0xfeedfacf)
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


if __name__ == '__main__':
    unittest.main()
