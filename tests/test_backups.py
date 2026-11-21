import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

import backups


class BackupTests(unittest.TestCase):
    def test_diff_handles_changed_blocks_growth_shrink_and_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = bytes(range(256)) * 1024
            expected = hashlib.sha256(original).hexdigest()
            backup, live, planned = (root / name for name in ('backup', 'live', 'planned'))
            backup.write_bytes(original)
            old = bytearray(original + b'new signature')
            old[100] ^= 1
            new = bytearray(original[:-1000])
            new[2 * backups.BLOCK_SIZE + 100] ^= 1
            live.write_bytes(old)
            planned.write_bytes(new)
            backups.write_diff(backup, original, [live, planned], expected)
            self.assertFalse(backup.exists())
            self.assertLess(backups.diff_path(backup).stat().st_size, len(original) // 10)
            for candidate in (original, old, new):
                live.write_bytes(candidate)
                self.assertEqual(backups.read_original(live, backup, expected), original)
            live.write_bytes(old)
            changed = bytearray(old)
            changed[backups.BLOCK_SIZE + 100] ^= 1
            live.write_bytes(changed)
            with self.assertRaisesRegex(RuntimeError, 'Original backup changed'):
                backups.read_original(live, backup, expected)

    def test_failed_diff_write_keeps_the_previous_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup, live = root / 'backup', root / 'live'
            original = b'original'
            expected = hashlib.sha256(original).hexdigest()
            backup.write_bytes(original)
            live.write_bytes(b'patched!')
            with patch.object(backups.os, 'replace', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    backups.write_diff(backup, original, [live], expected)
            self.assertEqual(backup.read_bytes(), original)
            backups.write_diff(backup, original, [live], expected)
            saved_diff = backups.diff_path(backup).read_bytes()
            with patch.object(backups.os, 'replace', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    backups.write_diff(backup, original, [live], expected)
            self.assertEqual(backups.diff_path(backup).read_bytes(), saved_diff)
            self.assertEqual(backups.read_original(live, backup, expected), original)

    def test_damaged_and_invalid_diffs_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup, live = root / 'backup', root / 'live'
            live.write_bytes(b'original')
            expected = hashlib.sha256(live.read_bytes()).hexdigest()
            invalid = [b'damaged', zlib.compress(b'{}')]
            for record in (
                    {'version': 2, 'size': 8, 'blocks': []},
                    {'version': 1, 'size': -1, 'blocks': []},
                    {'version': 1, 'size': 8, 'blocks': [[-1, '00']]},
                    {'version': 1, 'size': 8, 'blocks': [[0, '00']]},
                    {'version': 1, 'size': 9, 'blocks': []},
                    {'version': 1, 'size': 8, 'blocks': [[0, b'wrong!!!'.hex()]]},
                    {'version': 1, 'size': 8, 'blocks': [[0, live.read_bytes().hex()]] * 2}):
                invalid.append(zlib.compress(json.dumps(record).encode()))
            for data in invalid:
                with self.subTest(data=data):
                    backups.diff_path(backup).write_bytes(data)
                    with self.assertRaises(RuntimeError):
                        backups.read_original(live, backup, expected)
