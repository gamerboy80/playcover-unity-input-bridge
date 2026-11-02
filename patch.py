#!/usr/bin/env python3
"""Profile-locked native Unity input patch; local backups never enter Git."""
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

from profiles import DEFAULT_PROFILE, PROFILE_ALIASES, instruction_patches, load_profile, require, select_profile

ROOT = Path(__file__).resolve().parent
LIBRARY = 'Frameworks/NativeInputBridge.dylib'


def app_paths(profile):
    binary = profile['framework_binary']
    return binary, str(Path(binary).parent), profile['executable']


def local_directory(profile):
    local = ROOT / '.local'
    # Preserve existing backup locations and accept only known aliases of this identity.
    candidates = [local, local / profile['id']]
    candidates += [local / alias for alias, canonical in PROFILE_ALIASES.items()
                   if canonical == profile['id']]
    matches = []
    for candidate in candidates:
        state_path = candidate / 'state.json'
        if not state_path.exists():
            continue
        state = json.loads(state_path.read_text())
        if state.get('original', {}).get(profile['framework_binary']) == profile['original_sha256']:
            recorded = state.get('profile', profile['id'])
            require(PROFILE_ALIASES.get(recorded, recorded) == profile['id'], 'Legacy profile mismatch')
            matches.append(candidate)
    require(len(matches) <= 1, 'Multiple matching installation states; resolve duplicate backups first')
    if matches:
        return matches[0]
    return local / profile['id']


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def run(*args):
    subprocess.run(args, check=True)


def save_state(state, local):
    state_path = local / 'state.json'
    temporary = state_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, indent=2) + '\n')
    temporary.replace(state_path)


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


def closed(profile):
    result = subprocess.run(['/usr/bin/pgrep', '-x', profile['executable']], capture_output=True)
    require(result.returncode == 1, f'Quit {profile["game"]} before changing its files.')


def patch_instructions(binary, profile):
    patches = instruction_patches(profile)
    before = bytes(binary)
    for offset, expected, replacement in patches:
        require(before[offset:offset + len(expected)] == expected,
                f'Unexpected instructions at {offset:#x}')
        binary[offset:offset + len(expected)] = replacement
    cursor = 0
    for offset, expected, replacement in sorted(patches):
        require(binary[cursor:offset] == before[cursor:offset], 'Unintended patch change')
        require(binary[offset:offset + len(expected)] == replacement, 'Patch failed')
        cursor = offset + len(expected)
    require(binary[cursor:] == before[cursor:], 'Unintended trailing change')
    return binary


def link_library(binary):
    require(len(binary) >= 32 and struct.unpack_from('<I', binary)[0] == 0xfeedfacf,
            'Expected a thin 64-bit Mach-O executable')
    require(struct.unpack_from('<I', binary, 4)[0] == 0x100000c, 'Expected an arm64 executable')
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


def restore_files(app, profile, local):
    BINARY, FRAMEWORK, MAIN = app_paths(profile)
    BACKUP = local / 'original'
    for relative in (BINARY, MAIN):
        replace_file(BACKUP / relative, app / relative)
    for relative in (FRAMEWORK + '/_CodeSignature', '_CodeSignature'):
        replace_signature(BACKUP / relative, app / relative)
    (app / LIBRARY).unlink(missing_ok=True)


def check_installed(app, state, profile):
    recorded = state.get('profile', profile['id'])
    require(PROFILE_ALIASES.get(recorded, recorded) == profile['id'], 'Installation profile mismatch')
    require(state.get('original', {}).get(profile['framework_binary']) == profile['original_sha256'],
            'Profile does not match the recorded original framework')
    require(state['app'] == str(app), 'Backup belongs to a different app')
    for relative, expected in state['installed'].items():
        require((app / relative).is_file() and digest(app / relative) == expected,
                f'{relative} changed since installation; refusing to overwrite it')


def build(profile):
    run('/bin/sh', str(ROOT / 'build.sh'), profile['id'])


def stage_framework(directory, profile, local):
    BINARY, FRAMEWORK, _ = app_paths(profile)
    BACKUP = local / 'original'
    require(digest(BACKUP / BINARY) == profile['original_sha256'], 'Original framework backup changed')
    framework = directory / Path(FRAMEWORK).name
    shutil.copytree(BACKUP / FRAMEWORK, framework, symlinks=True)
    (framework / Path(BINARY).name).write_bytes(
        patch_instructions(bytearray((BACKUP / BINARY).read_bytes()), profile))
    run('/usr/bin/codesign', '--force', '--sign', '-', str(framework))
    run('/usr/bin/codesign', '--verify', '--strict', str(framework))
    return framework


def install(app, profile, local):
    BINARY, FRAMEWORK, MAIN = app_paths(profile)
    BACKUP = local / 'original'
    STATE = local / 'state.json'
    closed(profile)
    require(not STATE.exists() and not BACKUP.exists(),
            'Local backup/state already exists; use status, update, or restore.')
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    require(info.get('CFBundleIdentifier') == profile['bundle_id'] and
            info.get('CFBundleShortVersionString') == profile['version'] and
            info.get('CFBundleExecutable') == MAIN, 'App identity/version does not match the profile')
    require(os.access(app / MAIN, os.X_OK), 'Game executable is missing its execute permission')
    require(digest(app / BINARY) == profile['original_sha256'],
            'Unsupported framework hash; restore earlier patches first and select an exact matching profile.')
    require(not (app / LIBRARY).exists(), 'A native input bridge is already installed')
    build(profile)
    local.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir()
    # Copy originals before any app mutation. Retain them if signing fails.
    shutil.copytree(app / FRAMEWORK, BACKUP / FRAMEWORK, symlinks=True)
    shutil.copy2(app / MAIN, BACKUP / MAIN)
    shutil.copytree(app / '_CodeSignature', BACKUP / '_CodeSignature')
    original = {p: digest(BACKUP / p) for p in (BINARY, MAIN)}
    state = {'profile': profile['id'], 'app': str(app), 'original': original, 'installed': {}, 'status': 'prepared'}
    with tempfile.TemporaryDirectory(dir=local) as tmp:
        staged = Path(tmp)
        framework = stage_framework(staged, profile, local)
        main = staged / MAIN
        main.write_bytes(link_library(bytearray((app / MAIN).read_bytes())))
        shutil.copystat(app / MAIN, main)
        save_state(state, local)
        try:
            replace_file(framework / Path(BINARY).name, app / BINARY)
            replace_signature(framework / '_CodeSignature', app / FRAMEWORK / '_CodeSignature')
            replace_file(main, app / MAIN)
            replace_file(ROOT / 'build' / profile['id'] / 'NativeInputBridge.dylib', app / LIBRARY)
            run('/usr/bin/codesign', '--force', '--sign', '-', '--preserve-metadata=entitlements', str(app))
            run('/usr/bin/codesign', '--verify', '--strict', str(app))
            state['profile'] = profile['id']
            state['installed'] = {p: digest(app / p) for p in (BINARY, MAIN, LIBRARY)}
            state['status'] = 'installed'
            save_state(state, local)
        except BaseException:
            restore_files(app, profile, local)
            state['status'] = 'restored'
            save_state(state, local)
            raise
    print(f'{profile["id"]} installed. Native capture is automatic; Option+M is an optional fallback.')


def restore(app, state, profile, local):
    BACKUP = local / 'original'
    closed(profile)
    require(state['status'] == 'installed', 'Expected an installed patch')
    check_installed(app, state, profile)
    for relative, expected in state['original'].items():
        require(digest(BACKUP / relative) == expected, 'Original backup changed')
    restore_files(app, profile, local)
    run('/usr/bin/codesign', '--verify', '--strict', str(app))
    state['status'] = 'restored'
    save_state(state, local)
    print(f'Original executable, framework, and signatures restored. Backup retained in {local}.')


def update(app, state, profile, local):
    BINARY, FRAMEWORK, MAIN = app_paths(profile)
    closed(profile)
    require(state['status'] == 'installed', 'Expected an installed patch')
    check_installed(app, state, profile)
    build(profile)
    with tempfile.TemporaryDirectory(dir=local) as tmp:
        previous = Path(tmp)
        shutil.copy2(app / LIBRARY, previous / 'bridge')
        shutil.copy2(app / MAIN, previous / MAIN)
        shutil.copytree(app / '_CodeSignature', previous / '_CodeSignature')
        shutil.copy2(app / BINARY, previous / 'UnityFramework')
        shutil.copytree(app / FRAMEWORK / '_CodeSignature', previous / 'framework-signature')
        framework = stage_framework(previous, profile, local)
        try:
            replace_file(framework / Path(BINARY).name, app / BINARY)
            replace_signature(framework / '_CodeSignature', app / FRAMEWORK / '_CodeSignature')
            replace_file(ROOT / 'build' / profile['id'] / 'NativeInputBridge.dylib', app / LIBRARY)
            run('/usr/bin/codesign', '--force', '--sign', '-', '--preserve-metadata=entitlements', str(app))
            run('/usr/bin/codesign', '--verify', '--strict', str(app))
            state['profile'] = profile['id']
            state['installed'] = {p: digest(app / p) for p in (BINARY, MAIN, LIBRARY)}
            save_state(state, local)
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
    parser.add_argument('command', choices=['profiles', 'build', 'install', 'update', 'restore', 'status'])
    parser.add_argument('--profile', help='ID from profiles/*.json; auto-selected when --app is supplied')
    parser.add_argument('--app', type=Path, help="Override the profile bundle's PlayCover location")
    args = parser.parse_args()
    if args.command == 'profiles':
        for path in sorted((ROOT / 'profiles').glob('*.json')):
            profile = load_profile(path.stem)
            suffix = ' [test only; select explicitly]' if profile.get('test_only') else ''
            print(f'{profile["id"]}: {profile["game"]} {profile["version"]} ({profile["bundle_id"]}){suffix}')
        return
    app = args.app.expanduser().resolve() if args.app else None
    profile = (select_profile(plistlib.loads((app / 'Info.plist').read_bytes()), args.profile)
               if app else load_profile(args.profile or DEFAULT_PROFILE))
    local = local_directory(profile)
    app = (app or Path.home() / 'Library/Containers/io.playcover.PlayCover/Applications' /
           (profile['bundle_id'] + '.app')).expanduser().resolve()
    print(f'Selected profile: {profile["id"]}')
    if args.command != 'build':
        select_profile(plistlib.loads((app / 'Info.plist').read_bytes()), profile['id'])
    for kind in ('keyboard_mouse', 'trackpad'):
        note = profile['validation'][kind]
        if note.lower().startswith(('experimental', 'physical test failed')):
            print(f'Warning ({kind}): {note}')
    if args.command == 'build':
        build(profile)
    elif args.command == 'install':
        install(app, profile, local)
    else:
        state_path = local / 'state.json'
        require(state_path.exists(), 'No local installation state for this profile')
        state = json.loads(state_path.read_text())
        require(state['app'] == str(app), 'Backup belongs to a different app')
        if args.command == 'status':
            if state['status'] == 'installed':
                check_installed(app, state, profile)
            print(json.dumps(state, indent=2))
        elif args.command == 'restore':
            restore(app, state, profile, local)
        else:
            update(app, state, profile, local)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
