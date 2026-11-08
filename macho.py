"""Minimal arm64 Mach-O dylib load-command editing for the patch installers."""
import struct


def _commands(binary):
    if len(binary) < 32 or struct.unpack_from('<I', binary)[0] != 0xfeedfacf:
        raise RuntimeError('Expected a thin 64-bit Mach-O executable')
    if struct.unpack_from('<I', binary, 4)[0] != 0x100000c:
        raise RuntimeError('Expected an arm64 executable')
    count, size = struct.unpack_from('<II', binary, 16)
    end = 32 + size
    if end > len(binary):
        raise RuntimeError('Invalid Mach-O header size')
    commands = []
    first_section = len(binary)
    pos = 32
    for _ in range(count):
        if pos + 8 > end:
            raise RuntimeError('Truncated load command')
        cmd, length = struct.unpack_from('<II', binary, pos)
        if length < 8 or length % 8 or pos + length > end:
            raise RuntimeError('Invalid load command size')
        if cmd == 0x19:
            if length < 72:
                raise RuntimeError('Truncated segment')
            sections = struct.unpack_from('<I', binary, pos + 64)[0]
            if 72 + sections * 80 > length:
                raise RuntimeError('Truncated section table')
            for index in range(sections):
                offset = struct.unpack_from('<I', binary, pos + 72 + index * 80 + 48)[0]
                if offset:
                    first_section = min(first_section, offset)
        commands.append((pos, cmd, length))
        pos += length
    if pos != end:
        raise RuntimeError('Load command count mismatch')
    return commands, end, first_section


def dylibs(binary):
    result = []
    for pos, cmd, length in _commands(binary)[0]:
        if cmd not in (0xc, 0x80000018, 0x8000001f, 0x20, 0x80000023):
            continue
        result.append((cmd, _dylib_name(binary, pos, length)))
    return result


def _dylib_name(binary, pos, length):
    name_offset = struct.unpack_from('<I', binary, pos + 8)[0]
    if name_offset < 24 or name_offset >= length:
        raise RuntimeError('Invalid dylib load-command name offset')
    end = bytes(binary).find(b'\0', pos + name_offset, pos + length)
    if end < 0:
        raise RuntimeError('Unterminated dylib load-command name')
    try:
        return bytes(binary[pos + name_offset:end]).decode('utf-8')
    except UnicodeDecodeError as error:
        raise RuntimeError('Invalid dylib load-command name') from error


def has_dylib(binary, path):
    return any(name == path for _, name in dylibs(binary))


def executable_content(binary):
    """Compare code/load commands across registered ad-hoc re-signing operations."""
    commands = _commands(binary)[0]
    signatures = [(pos, size) for pos, cmd, size in commands if cmd == 0x1d]
    if not signatures:
        return bytes(binary)
    if len(signatures) != 1 or signatures[0][1] != 16:
        raise RuntimeError('Invalid executable code-signature command')
    pos = signatures[0][0]
    start, size = struct.unpack_from('<II', binary, pos + 8)
    if start < 32 + struct.unpack_from('<I', binary, 20)[0] or start + size != len(binary):
        raise RuntimeError('Executable signature must occupy the end of the file')
    result = bytearray(binary[:start])
    struct.pack_into('<I', result, pos + 12, 0)
    for offset, cmd, _ in commands:
        if cmd == 0x19 and binary[offset + 8:offset + 24].rstrip(b'\0') == b'__LINKEDIT':
            file_offset, file_size = struct.unpack_from('<QQ', binary, offset + 40)
            if file_offset > start or file_offset + file_size != len(binary):
                raise RuntimeError('Unexpected executable link-edit range')
            struct.pack_into('<Q', result, offset + 32, 0)
            struct.pack_into('<Q', result, offset + 48, start - file_offset)
    return bytes(result)


def add_dylib(binary, path):
    if has_dylib(binary, path):
        raise RuntimeError(f'Dylib load command already exists: {path}')
    commands, end, first_section = _commands(binary)
    encoded = path.encode('utf-8') + b'\0'
    cmdsize = (24 + len(encoded) + 7) & ~7
    if end + cmdsize > first_section or any(binary[end:end + cmdsize]):
        raise RuntimeError('Not enough unused header padding for the dylib load command')
    command = struct.pack('<6I', 0xc, cmdsize, 24, 0, 0, 0) + encoded
    binary[end:end + cmdsize] = command + bytes(cmdsize - len(command))
    struct.pack_into('<II', binary, 16, len(commands) + 1, end - 32 + cmdsize)
    return binary


def remove_dylib(binary, path, required=True):
    commands, end, _ = _commands(binary)
    matches = []
    for pos, cmd, length in commands:
        if cmd != 0xc:
            continue
        if _dylib_name(binary, pos, length) == path:
            matches.append((pos, length))
    if not matches:
        if required:
            raise RuntimeError(f'Dylib load command is not present: {path}')
        return binary
    if len(matches) != 1:
        raise RuntimeError(f'Expected one dylib load command for {path}, found {len(matches)}')
    pos, length = matches[0]
    remaining = end - (pos + length)
    binary[pos:pos + remaining] = binary[pos + length:end]
    binary[end - length:end] = bytes(length)
    struct.pack_into('<II', binary, 16, len(commands) - 1, end - 32 - length)
    return binary
