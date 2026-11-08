"""Read-only, fail-closed ARM64/IL2CPP profile resolution. No runtime dependencies."""
import bisect
import copy
import hashlib
import json
import struct

from macho import _commands
from profiles import require, validate


def unique(values, label):
    values = list(dict.fromkeys(values))
    require(len(values) == 1, f'{label}: expected one verified match, found {len(values)}. This build needs review.')
    return values[0]


def matches(data, pattern, mask):
    return len(data) == len(pattern) and all((a & m) == (b & m) for a, b, m in zip(data, pattern, mask))


def scan(data, pattern, mask, start=0, end=None, alignment=4):
    require(len(pattern) == len(mask) and len(pattern) > 0, 'Invalid signature length')
    end = len(data) if end is None else end
    runs, begin = [], None
    for i, value in enumerate(mask + b'\0'):
        if value == 255 and begin is None:
            begin = i
        elif value != 255 and begin is not None:
            runs.append((begin, i))
            begin = None
    require(runs, 'A signature needs fixed bytes')
    lo, hi = max(runs, key=lambda pair: pair[1] - pair[0])
    require(hi - lo >= 2, 'A signature needs at least two consecutive fixed bytes')
    cursor = start + lo
    while cursor < end:
        found = data.find(pattern[lo:hi], cursor, end)
        if found < 0:
            break
        cursor = found + 1
        pos = found - lo
        if pos >= start and pos % alignment == 0 and pos + len(pattern) <= end and matches(data[pos:pos + len(pattern)], pattern, mask):
            yield pos


class Image:
    def __init__(self, data):
        self.data = data
        self.segments, self.sections, self.functions = [], {}, []
        for pos, cmd, size in _commands(data)[0]:
            if cmd == 0x19:
                name = data[pos + 8:pos + 24].rstrip(b'\0').decode()
                vm, length, offset, stored = struct.unpack_from('<4Q', data, pos + 24)
                require(offset + stored <= len(data), 'Truncated Mach-O segment')
                self.segments.append((name, vm, length, offset, stored))
                for i in range(struct.unpack_from('<I', data, pos + 64)[0]):
                    q = pos + 72 + i * 80
                    section = data[q:q + 16].rstrip(b'\0').decode()
                    addr, count, file_offset = struct.unpack_from('<QQI', data, q + 32)
                    self.sections[(name, section)] = (addr, count, file_offset)
            elif cmd == 0x26:
                offset, length = struct.unpack_from('<II', data, pos + 8)
                require(offset + length <= len(data), 'Truncated function-start table')
                address, value, shift = 0, 0, 0
                for byte in data[offset:offset + length]:
                    value |= (byte & 127) << shift
                    require(shift <= 63, 'Invalid function-start delta')
                    if byte & 128:
                        shift += 7
                    else:
                        if value == 0:
                            break
                        address += value
                        self.functions.append(address)
                        value, shift = 0, 0
            elif cmd == 0x2c:
                require(struct.unpack_from('<I', data, pos + 16)[0] == 0, 'Encrypted frameworks cannot be resolved')
        require(('__TEXT', '__text') in self.sections and self.functions, 'Missing executable sections or function boundaries')
        base = next(vm for name, vm, _, _, _ in self.segments if name == '__TEXT')
        self.functions = [base + value for value in self.functions]
        self.function_set = set(self.functions)

    def file(self, address, size=1, segment=None):
        for name, vm, _, offset, stored in self.segments:
            if vm <= address and address + size <= vm + stored and (segment is None or name == segment):
                return offset + address - vm
        raise RuntimeError(f'Address {address:#x} is outside the required file-backed segment')

    def vm(self, offset):
        for _, vm, _, start, stored in self.segments:
            if start <= offset < start + stored:
                return vm + offset - start
        raise RuntimeError('File offset is outside Mach-O segments')

    def code(self, address):
        start, count, _ = self.sections['__TEXT', '__text']
        return address % 4 == 0 and start <= address < start + count

    def body(self, address):
        require(self.code(address) and address in self.function_set, f'{address:#x} is not a function entry')
        index = bisect.bisect_right(self.functions, address)
        end = self.functions[index] if index < len(self.functions) else address + 4096
        pos = self.file(address, end - address)
        return self.data[pos:pos + end - address]


class Metadata:
    """Detect the examined unencrypted record layout by independent sentinel records."""
    def __init__(self, data):
        self.data = data
        sentinel = b'mscorlib\0\0mscorlib.dll\0<Module>\0Locale\0.ctor\0'
        self.strings = unique(scan(data, sentinel, b'\xff' * len(sentinel), alignment=1), 'Metadata string pool')
        # Name and token fields identify the type table without using header offsets.
        candidates = []
        for pos in scan(data, struct.pack('<I', 23), b'\xff' * 4):
            start = pos - 40
            if start >= 0 and start + 160 <= len(data):
                if (struct.unpack_from('<I', data, start + 20)[0] == 0x02000001 and
                    struct.unpack_from('<I', data, start + 100)[0] == 0x02000002 and
                    struct.unpack_from('<I', data, start + 120)[0] == 32):
                    candidates.append(start)
        self.types = unique(candidates, 'IL2CPP type records')
        ctor = struct.pack('<II', 1, 39)
        candidates = []
        for pos in scan(data, ctor, b'\xff' * 8):
            if pos + 90 <= len(data) and data[pos + 30:pos + 38] == struct.pack('<II', 1, 49) and data[pos + 60:pos + 68] == struct.pack('<II', 1, 49):
                candidates.append(pos)
        self.methods = unique(candidates, 'IL2CPP method records')
        self.classes = {}
        for index in range(min(200000, (len(data) - self.types) // 80)):
            row = struct.unpack_from('<20I', data, self.types + index * 80)
            if row[5] >> 24 != 2:
                break
            name, namespace = self.text(row[10]), self.text(row[2])
            self.classes.setdefault((namespace, name), []).append((index, row[1]))
        require(len(self.classes) > 100, 'Metadata type table is incomplete')

    def text(self, offset):
        if offset == 0xffffffff:
            return ''
        require(offset < 32 * 1024 * 1024 and self.strings + offset < len(self.data), 'Invalid metadata string index')
        start = self.strings + offset
        end = self.data.find(b'\0', start, start + 4096)
        require(end >= 0, 'Unterminated metadata name')
        try:
            return self.data[start:end].decode('utf-8')
        except UnicodeDecodeError as error:
            raise RuntimeError('Metadata names use an unsupported encoding') from error

    def method(self, spec):
        namespace, name = spec['namespace'], spec['class']
        results = []
        for index, first in self.classes.get((namespace, name), []):
            if first == 0xffffffff:
                continue
            for j in range(first, first + 20000):
                pos = self.methods + j * 30
                require(pos + 30 <= len(self.data), 'Truncated method table')
                declaring, string = struct.unpack_from('<II', self.data, pos)
                if declaring != index:
                    break
                if self.text(string) == spec['method'] and struct.unpack_from('<H', self.data, pos + 20)[0] == spec['parameters']:
                    token = struct.unpack_from('<I', self.data, pos + 22)[0]
                    require(token >> 24 == 6, 'Invalid method token')
                    results.append(token & 0xffffff)
        return unique(results, f'{namespace}.{name}.{spec["method"]}')


def rule_bytes(rule):
    pattern = bytes.fromhex(rule['pattern'])
    mask = bytes.fromhex(rule.get('mask', 'ff' * len(pattern)))
    require(len(pattern) == len(mask) and 4 <= len(pattern) <= 4096 and len(pattern) % 4 == 0, 'Invalid ARM64 signature')
    return pattern, mask


def resolve_functions(image, metadata, rules):
    resolved, modules = {}, {}
    for name, rule in rules.items():
        if 'method' in rule:
            require(metadata is not None, 'Managed method resolution requires supported metadata')
            modules.setdefault(rule['module'], []).append((name, rule, metadata.method(rule)))
        else:
            pattern, mask = rule_bytes(rule)
            _, count, start = image.sections['__TEXT', '__text']
            position = unique(scan(image.data, pattern, mask, start, start + count), name)
            address = image.vm(position) - rule.get('offset', 0)
            image.body(address)
            resolved[name] = address
    for module, members in modules.items():
        needle = b'\0' + module.encode() + b'\0'
        string = unique(scan(image.data, needle, b'\xff' * len(needle), alignment=1), module) + 1
        refs = [pos for pos in scan(image.data, struct.pack('<I', image.vm(string) & 0xffffffff), b'\xff' * 4, alignment=8)
                if pos + 8 <= len(image.data) and struct.unpack_from('<Q', image.data, pos)[0] & 0xfffffffff == image.vm(string)]
        candidates = []
        for ref in refs:
            if not any(name != '__TEXT' and off <= ref < off + stored for name, _, _, off, stored in image.segments):
                continue
            for delta in range(-80, 81, 8):
                if ref + delta < 0 or ref + delta + 8 > len(image.data):
                    continue
                pointer = struct.unpack_from('<Q', image.data, ref + delta)[0] & 0xfffffffff
                for bias in (-1, -2):
                    found = {}
                    try:
                        for name, rule, token in members:
                            entry = image.file(pointer + (token + bias) * 8, 8)
                            address = struct.unpack_from('<Q', image.data, entry)[0] & 0xfffffffff
                            body = image.body(address)
                            pattern, mask = rule_bytes(rule)
                            offset = rule.get('offset', 0)
                            if not matches(body[offset:offset + len(pattern)], pattern, mask):
                                break
                            found[name] = address
                        else:
                            candidates.append(tuple(sorted(found.items())))
                    except RuntimeError:
                        continue
        resolved.update(dict(unique(candidates, f'{module} method table and ABI signatures')))
    return resolved


def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def decode(image, address, kind):
    if kind == 'return-pc':
        previous = struct.unpack_from('<I', image.data, image.file(address - 4, 4))[0]
        require(previous & 0xfffffc1f == 0xd63f0000, 'Expected BLR before input return address')
        return address
    pos = image.file(address, 16)
    a, b, c, d = struct.unpack_from('<4I', image.data, pos)
    if kind in ('adrp-add', 'adrp-add-load'):
        require(a & 0x9f000000 == 0x90000000 and b & 0xffc00000 == 0x91000000 and
                (a & 31) == ((b >> 5) & 31) == (b & 31), 'Invalid ADRP/ADD register chain')
        value = ((address & ~4095) + signed(((a >> 5) & 0x7ffff) * 4 + ((a >> 29) & 3), 21) * 4096 + ((b >> 10) & 4095))
        if kind == 'adrp-add-load':
            require(c & 0xffc00000 == 0xf9400000 and ((c >> 5) & 31) == (b & 31), 'Invalid global load chain')
            value += ((c >> 10) & 4095) * 8
        return value
    if kind == 'add-load':
        require(a & 0xff000000 == 0x91000000 and b & 0x3b400000 == 0x39400000 and
                (a & 31) == ((b >> 5) & 31), 'Invalid ADD/load register chain')
        return (((a >> 10) & 4095) << (12 if a & (1 << 22) else 0)) + (((b >> 10) & 4095) << (b >> 30))
    if kind == 'load':
        require(a & 0x3b400000 == 0x39400000, 'Expected an unsigned load')
        return ((a >> 10) & 4095) << (a >> 30)
    if kind == 'pair-load':
        require(a & 0xffc00000 == 0xa9400000, 'Expected a 64-bit pair load')
        value = signed((a >> 15) & 127, 7) * 8
        require(value >= 0, 'Negative object-field offset')
        return value
    if kind == 'mov32':
        require(a & 0xffe00000 == 0x52800000 and b & 0xffe00000 == 0x72a00000 and
                (a & 31) == (b & 31), 'Expected MOVZ/MOVK offset pair')
        return ((a >> 5) & 65535) | (((b >> 5) & 65535) << 16)
    raise RuntimeError(f'Unknown extraction: {kind}')


def resolve_profile(binary, metadata_bytes, template, contract, version):
    require(contract['schema_version'] == 1 and contract['bundle_id'] == template['bundle_id'], 'Invalid signature contract')
    image = Image(binary)
    require(contract.get('metadata', 'zzz') in ('zzz', 'none'), 'Unsupported metadata resolution mode')
    metadata = Metadata(metadata_bytes) if contract.get('metadata', 'zzz') == 'zzz' else None
    functions = resolve_functions(image, metadata, contract['functions'])
    values, evidence = {}, {}
    for name, rule in contract['extract'].items():
        body = image.body(functions[rule['function']])
        pattern, mask = rule_bytes(rule)
        offset = unique(scan(body, pattern, mask), name)
        at = functions[rule['function']] + offset + rule.get('offset', 0)
        value = decode(image, at, rule['kind'])
        require(rule.get('minimum', 0) <= value <= rule.get('maximum', 2**64 - 1), f'{name}: implausible resolved value')
        require(value % rule.get('alignment', 1) == 0, f'{name}: misaligned resolved value')
        values[name] = value
        evidence[name] = {'function': rule['function'], 'instruction': hex(at), 'value': hex(value)}
    for left, right in contract['equal']:
        require(values[left] == values[right], f'Cross-check failed: {left} differs from {right}')
    result = copy.deepcopy(template)
    suffix = '-platform-pc-settings-test' if template.get('test_only') else ''
    result.update(id=f'{template["bundle_id"]}-{version}{suffix}', version=version,
                  original_sha256=hashlib.sha256(binary).hexdigest())
    for name, source in contract['addresses'].items():
        value = functions[source] if source in functions else values[source]
        if name == 'Statics' or name.endswith('Slot'):
            require(any(segment == '__DATA' and vm <= value and value + 8 <= vm + size
                        for segment, vm, size, _, _ in image.segments), f'{name} is outside writable data')
        else:
            require(image.code(value), f'{name} is outside executable code')
        result['bridge']['addresses'][name] = hex(value)
    for name, source in contract['fields'].items():
        result['bridge']['fields'][name] = hex(values[source])
    for patch in result['patches']:
        rule = contract['patches'][patch['name']]
        body = image.body(functions[rule['function']])
        pattern, mask = rule_bytes(rule)
        found = unique(scan(body, pattern, mask), patch['name'])
        offset = image.file(functions[rule['function']] + found + rule.get('offset', 0))
        expected = bytes.fromhex(rule['expected'])
        actual = binary[offset:offset + len(expected)]
        require(matches(actual, expected, bytes.fromhex(rule.get('expected_mask', 'ff' * len(expected)))),
                f'{patch["name"]}: replacement ABI changed')
        replacement = bytes.fromhex(rule['replacement'])
        if 'call_to' in rule:
            require(len(actual) == 4 and struct.unpack('<I', actual)[0] & 0xfc000000 == 0x94000000, 'Expected direct BL for redirected call')
            delta = functions[rule['call_to']] - image.vm(offset)
            require(delta % 4 == 0 and -(1 << 27) <= delta < (1 << 27), 'Redirected call is out of range')
            replacement = struct.pack('<I', 0x94000000 | ((delta // 4) & 0x3ffffff))
        if 'branch_to' in rule:
            target_pattern, target_mask = rule_bytes(rule['branch_to'])
            target = unique(scan(body, target_pattern, target_mask), patch['name'] + ' return path')
            delta = image.file(functions[rule['function']] + target) - (offset + len(replacement) - 4)
            require(delta % 4 == 0 and -(1 << 27) <= delta < (1 << 27), 'Patch branch target is out of range')
            replacement = replacement[:-4] + struct.pack('<I', 0x14000000 | ((delta // 4) & 0x3ffffff))
        patch.update(file_offset=hex(offset), expected=actual.hex(), replacement=replacement.hex())
    if template['bridge']['backend'] == 'unity-input-system-v1':
        result['bridge']['addresses']['ReadVector2'] = '0x0'
    result['resolution'] = {'contract': contract['id'],
                            'contract_sha256': hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest(),
                            'metadata_sha256': hashlib.sha256(metadata_bytes).hexdigest(),
                            'functions': {k: hex(v) for k, v in functions.items()}, 'extractions': evidence,
                            'runtime_validated': False}
    result['validation']['keyboard_mouse'] = 'Resolved from verified native signatures and backend layout checks. Physical gameplay verification pending.'
    result['validation']['trackpad'] = 'Shared trackpad conversion retained. Physical verification pending on this build.'
    return validate(result, result['id'])
