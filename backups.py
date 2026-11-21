"""Reverse block diffs for large binaries; originals are verified after reconstruction."""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zlib

from profiles import require

BLOCK_SIZE = 64 * 1024


def diff_path(backup):
    return backup.with_name(backup.name + '.reverse-diff')


def read_original(live, backup, expected):
    try:
        if backup.is_file():
            original = bytearray(backup.read_bytes())
        else:
            record = json.loads(zlib.decompress(diff_path(backup).read_bytes()))
            require(record['version'] == 1 and type(record['size']) is int and record['size'] >= 0,
                    'Invalid original backup diff')
            chunks = []
            end = 0
            for offset, encoded in record['blocks']:
                block = bytes.fromhex(encoded)
                require(type(offset) is int and offset >= end and offset % BLOCK_SIZE == 0 and
                        len(block) == min(BLOCK_SIZE, record['size'] - offset) and block,
                        'Invalid original backup diff block')
                chunks.append((offset, block))
                end = offset + len(block)
            original = bytearray(live.read_bytes())
            require(record['size'] <= len(original) + sum(len(block) for _, block in chunks),
                    'Truncated original backup diff')
            del original[record['size']:]
            original.extend(b'\0' * (record['size'] - len(original)))
            for offset, block in chunks:
                original[offset:offset + len(block)] = block
    except (OSError, ValueError, TypeError, KeyError, zlib.error) as error:
        raise RuntimeError('Original backup changed or its diff is unreadable') from error
    require(hashlib.sha256(original).hexdigest() == expected, 'Original backup changed')
    return original


def write_diff(backup, original, candidates, expected):
    """Save original blocks changed in either live or planned files before app writes."""
    require(hashlib.sha256(original).hexdigest() == expected, 'Original backup changed')
    blocks = []
    with ExitStack() as stack:
        sources = [stack.enter_context(path.open('rb')) for path in candidates]
        for offset in range(0, len(original), BLOCK_SIZE):
            block = original[offset:offset + BLOCK_SIZE]
            # Read every source even after a mismatch so their offsets stay aligned.
            changed = [source.read(len(block)) != block for source in sources]
            if any(changed):
                blocks.append((offset, block.hex()))
    data = zlib.compress(json.dumps({'version': 1, 'size': len(original), 'blocks': blocks}).encode())
    destination = diff_path(backup)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.diff-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, destination)
    finally:
        Path(name).unlink(missing_ok=True)
    # A complete diff is committed before retiring a legacy full binary backup.
    backup.unlink(missing_ok=True)
