#!/usr/bin/env python3
"""Version-locked ZZZ 3.3.0 desktop input patch; local backups never enter Git."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / '.local'
STATE = LOCAL / 'state.json'
BACKUP = LOCAL / 'original'
LIBRARY = 'Frameworks/NativeInputBridge.dylib'
FRAMEWORK = 'Frameworks/UnityFramework.framework'
BINARY = FRAMEWORK + '/UnityFramework'
MAIN = 'ZenlessZoneZero'
ORIGINAL_HASH = '8514f6ecf03272586a5c722db0d407608b5b28e9815b046e7b3f71ce588ee037'
PATCHES = (
    (0xc22d6b8, bytes.fromhex('f44fbea9fd7b01a9'), bytes.fromhex('40008052c0035fd6')),
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def run(*args):
    subprocess.run(args, check=True)


def save_state(state):
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, indent=2) + '\n')
    temporary.replace(STATE)


def replace_file(source, target):
    fd, name = tempfile.mkstemp(prefix=target.name + '.zzz-', dir=target.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        shutil.copy2(source, temporary)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def replace_signature(source, target):
    target.mkdir(exist_ok=True)
    for file in source.iterdir():
        require(file.is_file(), 'Unexpected signature directory')
        replace_file(file, target / file.name)
    for file in target.iterdir():
        if not (source / file.name).exists():
            require(file.is_file(), 'Unexpected signature resource')
            file.unlink()


def closed():
    result = subprocess.run(['/usr/bin/pgrep', '-x', MAIN], capture_output=True)
    require(result.returncode == 1, 'Quit Zenless Zone Zero before changing its files.')


def patch_instructions(binary):
    before = bytes(binary)
    for offset, expected, replacement in PATCHES:
        require(before[offset:offset + len(expected)] == expected,
                f'Unexpected instructions at {offset:#x}')
        binary[offset:offset + len(expected)] = replacement
    cursor = 0
    for offset, expected, replacement in sorted(PATCHES):
        require(binary[cursor:offset] == before[cursor:offset], 'Unintended patch change')
        require(binary[offset:offset + len(expected)] == replacement, 'Patch failed')
        cursor = offset + len(expected)
    require(binary[cursor:] == before[cursor:], 'Unintended trailing change')
    return binary


def link_library(binary):
    require(len(binary) >= 32 and struct.unpack_from('<I', binary)[0] == 0xfeedfacf,
            'Expected a thin 64-bit Mach-O executable')
    count, size = struct.unpack_from('<II', binary, 16)
    require(32 + size <= len(binary), 'Invalid Mach-O header size')
    pos, first_section = 32, len(binary)
    for _ in range(count):
        require(pos + 8 <= 32 + size, 'Truncated load command')
        cmd, length = struct.unpack_from('<II', binary, pos)
        require(length >= 8 and length % 8 == 0 and pos + length <= 32 + size,
                'Invalid load command size')
        if cmd == 0x19:
            require(length >= 72, 'Truncated segment')
            sections = struct.unpack_from('<I', binary, pos + 64)[0]
            require(72 + sections * 80 <= length, 'Truncated section table')
            for j in range(sections):
                offset = struct.unpack_from('<I', binary, pos + 72 + j * 80 + 48)[0]
                if offset:
                    first_section = min(first_section, offset)
        pos += length
    require(pos == 32 + size, 'Load command count mismatch')
    name = ('@executable_path/' + LIBRARY).encode() + b'\0'
    cmdsize = (24 + len(name) + 7) & ~7
    require(pos + cmdsize < first_section <= len(binary) and
            not any(binary[pos:pos + cmdsize]), 'Not enough unused header padding')
    before = bytes(binary)
    command = struct.pack('<6I', 0xc, cmdsize, 24, 0, 0, 0) + name
    binary[pos:pos + cmdsize] = command + bytes(cmdsize - len(command))
    struct.pack_into('<II', binary, 16, count + 1, size + cmdsize)
    require(len(binary) == len(before) and binary[first_section:] == before[first_section:],
            'Executable section changed')
    return binary


def restore_files(app):
    for relative in (BINARY, MAIN):
        replace_file(BACKUP / relative, app / relative)
    for relative in (FRAMEWORK + '/_CodeSignature', '_CodeSignature'):
        replace_signature(BACKUP / relative, app / relative)
    (app / LIBRARY).unlink(missing_ok=True)


def check_installed(app, state):
    require(state['app'] == str(app), 'Backup belongs to a different app')
    for relative, expected in state['installed'].items():
        require((app / relative).is_file() and digest(app / relative) == expected,
                f'{relative} changed since installation; refusing to overwrite it')


def build():
    run('/bin/sh', str(ROOT / 'build.sh'))


def stage_framework(directory):
    require(digest(BACKUP / BINARY) == ORIGINAL_HASH, 'Original framework backup changed')
    framework = directory / 'UnityFramework.framework'
    shutil.copytree(BACKUP / FRAMEWORK, framework, symlinks=True)
    (framework / 'UnityFramework').write_bytes(patch_instructions(bytearray((BACKUP / BINARY).read_bytes())))
    run('/usr/bin/codesign', '--force', '--sign', '-', str(framework))
    run('/usr/bin/codesign', '--verify', '--strict', str(framework))
    return framework


def install(app):
    closed()
    require(not STATE.exists() and not BACKUP.exists(),
            'Local backup/state already exists; use status, update, or restore.')
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    require(info.get('CFBundleIdentifier') == 'com.HoYoverse.Nap', 'Wrong app bundle')
    require(os.access(app / MAIN, os.X_OK), 'Game executable is missing its execute permission')
    require(digest(app / BINARY) == ORIGINAL_HASH,
            'Unsupported UnityFramework; restore earlier patches first. Only the documented 3.3.0 build is supported.')
    require(not (app / LIBRARY).exists(), 'A native input bridge is already installed')
    build()
    LOCAL.mkdir(exist_ok=True)
    BACKUP.mkdir()
    # Copy originals before any app mutation. Retain them if signing fails.
    shutil.copytree(app / FRAMEWORK, BACKUP / FRAMEWORK, symlinks=True)
    shutil.copy2(app / MAIN, BACKUP / MAIN)
    shutil.copytree(app / '_CodeSignature', BACKUP / '_CodeSignature')
    original = {p: digest(BACKUP / p) for p in (BINARY, MAIN)}
    state = {'app': str(app), 'original': original, 'installed': {}, 'status': 'prepared'}
    with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
        staged = Path(tmp)
        framework = stage_framework(staged)
        main = staged / MAIN
        main.write_bytes(link_library(bytearray((app / MAIN).read_bytes())))
        shutil.copystat(app / MAIN, main)
        save_state(state)
        try:
            replace_file(framework / 'UnityFramework', app / BINARY)
            replace_signature(framework / '_CodeSignature', app / FRAMEWORK / '_CodeSignature')
            replace_file(main, app / MAIN)
            replace_file(ROOT / 'build/NativeInputBridge.dylib', app / LIBRARY)
            run('/usr/bin/codesign', '--force', '--sign', '-', '--preserve-metadata=entitlements', str(app))
            run('/usr/bin/codesign', '--verify', '--strict', str(app))
            state['installed'] = {p: digest(app / p) for p in (BINARY, MAIN, LIBRARY)}
            state['status'] = 'installed'
            save_state(state)
        except BaseException:
            restore_files(app)
            state['status'] = 'restored'
            save_state(state)
            raise
    print('Desktop input patch installed. Option+M captures the pointer; Escape releases it.')


def restore(app, state):
    closed()
    require(state['status'] == 'installed', 'Expected an installed patch')
    check_installed(app, state)
    for relative, expected in state['original'].items():
        require(digest(BACKUP / relative) == expected, 'Original backup changed')
    restore_files(app)
    run('/usr/bin/codesign', '--verify', '--strict', str(app))
    state['status'] = 'restored'
    save_state(state)
    print('Original executable, framework, and signatures restored. Backup retained in .local/.')


def update(app, state):
    closed()
    require(state['status'] == 'installed', 'Expected an installed patch')
    check_installed(app, state)
    build()
    with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
        previous = Path(tmp)
        shutil.copy2(app / LIBRARY, previous / 'bridge')
        shutil.copy2(app / MAIN, previous / MAIN)
        shutil.copytree(app / '_CodeSignature', previous / '_CodeSignature')
        shutil.copy2(app / BINARY, previous / 'UnityFramework')
        shutil.copytree(app / FRAMEWORK / '_CodeSignature', previous / 'framework-signature')
        framework = stage_framework(previous)
        try:
            replace_file(framework / 'UnityFramework', app / BINARY)
            replace_signature(framework / '_CodeSignature', app / FRAMEWORK / '_CodeSignature')
            replace_file(ROOT / 'build/NativeInputBridge.dylib', app / LIBRARY)
            run('/usr/bin/codesign', '--force', '--sign', '-', '--preserve-metadata=entitlements', str(app))
            run('/usr/bin/codesign', '--verify', '--strict', str(app))
            state['installed'] = {p: digest(app / p) for p in (BINARY, MAIN, LIBRARY)}
            save_state(state)
        except BaseException:
            replace_file(previous / 'bridge', app / LIBRARY)
            replace_file(previous / MAIN, app / MAIN)
            replace_signature(previous / '_CodeSignature', app / '_CodeSignature')
            replace_file(previous / 'UnityFramework', app / BINARY)
            replace_signature(previous / 'framework-signature', app / FRAMEWORK / '_CodeSignature')
            raise
    print('Native input bridge updated; original backup retained.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'install', 'update', 'restore', 'status'])
    parser.add_argument('--app', type=Path,
                        default=Path.home() / 'Library/Containers/io.playcover.PlayCover/Applications/com.HoYoverse.Nap.app')
    args = parser.parse_args()
    app = args.app.expanduser().resolve()
    if args.command == 'build':
        build()
    elif args.command == 'install':
        install(app)
    else:
        require(STATE.exists(), 'No local installation state')
        state = json.loads(STATE.read_text())
        require(state['app'] == str(app), 'Backup belongs to a different app')
        if args.command == 'status':
            if state['status'] == 'installed':
                check_installed(app, state)
            print(json.dumps(state, indent=2))
        elif args.command == 'restore':
            restore(app, state)
        else:
            update(app, state)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
