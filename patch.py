#!/usr/bin/env python3
"""Profile-locked native Unity input patch; local backups never enter Git."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile

from profiles import DEFAULT_PROFILE, PROFILE_ALIASES, instruction_patches, load_profile, match_app, require, select_profile

ROOT = Path(__file__).resolve().parent
LIBRARY = 'Frameworks/NativeInputBridge.dylib'


def app_paths(profile):
    binary = profile['framework_binary']
    return binary, str(Path(binary).parent), profile['executable']


def profile_name(profile):
    return next((alias for alias, canonical in PROFILE_ALIASES.items()
                 if canonical == profile['id']), profile['id'])


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
    require(len(matches) <= 1,
            f'Multiple matching saved backups were found for {profile_name(profile)}. No files were changed. Inspect these folders before continuing: ' +
            ', '.join(str(path) for path in matches))
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
    try:
        subprocess.run(args, check=True)
    except FileNotFoundError as error:
        tool = Path(args[0]).name
        raise RuntimeError(f"Required tool '{tool}' was not found. Install Xcode Command Line Tools and try again.") from error


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


def read_app_info(app):
    require(app.is_dir(), f'Game app not found: {app}')
    info_path = app / 'Info.plist'
    try:
        return plistlib.loads(info_path.read_bytes())
    except (OSError, plistlib.InvalidFileException, ValueError) as error:
        raise RuntimeError(f"Couldn't read game details from {info_path}: {error}") from error


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
                f'A game file changed after patching. It may be from a game update; no files were changed.')


def applied_profile(app, info):
    applied = []
    changed = []
    for path in sorted((ROOT / 'profiles').glob('*.json')):
        profile = load_profile(path.stem)
        if not match_app(profile, info):
            continue
        local = local_directory(profile)
        state_path = local / 'state.json'
        if not state_path.exists():
            continue
        try:
            state = json.loads(state_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Couldn't read saved patch information at {state_path}: {error}") from error
        if not isinstance(state, dict) or state.get('app') != str(app):
            continue
        if state.get('status') == 'prepared':
            changed.append((profile, state, local, 'prepared'))
        elif state.get('status') == 'installed':
            try:
                check_installed(app, state, profile)
            except RuntimeError:
                original = state.get('original', {})
                restored = (bool(original) and
                            all((app / relative).is_file() and digest(app / relative) == expected
                                for relative, expected in original.items()) and
                            not (app / LIBRARY).exists())
                if not restored:
                    changed.append((profile, state, local, 'changed'))
            else:
                applied.append((profile, state, local, 'installed'))
    matches = applied or changed
    require(len(matches) <= 1,
            'More than one profile matches the game files. No changes were made; inspect the saved profile folders under .local before continuing.')
    return matches[0] if matches else None


def build(profile):
    print(f'Building the input bridge for {profile["game"]} {profile["version"]}...', flush=True)
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
    info = read_app_info(app)
    require(info.get('CFBundleIdentifier') == profile['bundle_id'] and
            info.get('CFBundleShortVersionString') == profile['version'] and
            info.get('CFBundleExecutable') == MAIN,
            f'This app does not match the selected {profile["game"]} {profile["version"]} profile.')
    require(os.access(app / MAIN, os.X_OK),
            'The game app is missing its executable file permission. Reinstall the app in PlayCover, then try again.')
    active = applied_profile(app, info)
    if active:
        active_profile, _, _, active_status = active
        app_option = f'--app {shlex.quote(str(app))}'
        if active_status == 'installed' and active_profile['id'] == profile['id']:
            raise RuntimeError(
                f'{profile_name(profile)} is already applied. Run `python3 patch.py update {app_option}` to update it, '
                f'or `python3 patch.py restore {app_option}` to remove it.')
        if active_status != 'installed':
            raise RuntimeError(
                f'{profile_name(active_profile)} needs attention before another profile can be applied. '
                'Run status --verbose to inspect it.')
        raise RuntimeError(
            f'{profile_name(active_profile)} is currently applied. To switch profiles, run '
            f'`python3 patch.py restore {app_option}`, then '
            f'`python3 patch.py apply --profile {profile_name(profile)} {app_option}`.')

    original = None
    if STATE.exists() or BACKUP.exists():
        require(STATE.is_file() and BACKUP.is_dir(),
                'The saved backup is incomplete. Keep it and run status --verbose before changing the game.')
        try:
            saved = json.loads(STATE.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Couldn't read saved patch information at {STATE}: {error}") from error
        require(isinstance(saved, dict) and saved.get('app') == str(app) and
                PROFILE_ALIASES.get(saved.get('profile'), saved.get('profile')) == profile['id'],
                'The saved backup belongs to a different app or profile.')
        require(saved.get('status') in ('restored', 'installed'),
                f'{profile_name(profile)} has an unfinished setup. Run status --verbose before trying again.')
        original = saved.get('original')
        require(isinstance(original, dict) and original.get(BINARY) == profile['original_sha256'],
                'The saved original files do not match this profile.')
        for relative in (BINARY, MAIN):
            expected = original.get(relative)
            require(expected and (BACKUP / relative).is_file() and digest(BACKUP / relative) == expected,
                    f'The saved original file {relative} is missing or has changed.')
            require((app / relative).is_file() and digest(app / relative) == expected,
                    'The game is not fully restored to its original files. Run status --verbose before trying again.')
        require((BACKUP / FRAMEWORK / '_CodeSignature').is_dir() and
                (BACKUP / '_CodeSignature').is_dir(),
                'The saved app signatures are missing. Keep this backup and inspect it before continuing.')
    require(digest(app / BINARY) == profile['original_sha256'],
            'These game files do not match the selected profile. Restore the original game files or choose a profile for this exact version.')
    require(not (app / LIBRARY).exists(),
            'An input bridge is already present in this app. Run status or restore before installing again.')
    build(profile)
    message = ('Using the saved backup of the original game files...'
               if original else 'Saving a backup of the original game files...')
    print(message, flush=True)
    local.mkdir(parents=True, exist_ok=True)
    if original is None:
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
            print('Installing the bridge and checking the app signature...', flush=True)
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
    print(f'Done. The input bridge is installed for {profile["game"]} {profile["version"]}.')
    print('Native mouse capture is enabled. Option+M remains available as a fallback.')


def restore(app, state, profile, local):
    BACKUP = local / 'original'
    closed(profile)
    require(state.get('status') == 'installed',
            f'{profile_name(profile)} is not currently patched, so there is nothing to restore. Run status to check the active profile.')
    check_installed(app, state, profile)
    for relative, expected in state['original'].items():
        require(digest(BACKUP / relative) == expected, 'Original backup changed')
    print(f'Restoring the original {profile["game"]} files...', flush=True)
    restore_files(app, profile, local)
    run('/usr/bin/codesign', '--verify', '--strict', str(app))
    state['status'] = 'restored'
    save_state(state, local)
    print('Done. The original game files are restored. The backup is kept for future installs.')


def update(app, state, profile, local):
    BINARY, FRAMEWORK, MAIN = app_paths(profile)
    closed(profile)
    require(state.get('status') == 'installed',
            f'{profile_name(profile)} is not currently patched, so there is nothing to update. Run status to check the active profile.')
    check_installed(app, state, profile)
    build(profile)
    print('Updating the bridge and checking the app signature...', flush=True)
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
    print('Done. The input bridge is updated. Your original backup is unchanged.')


def print_status(state, profile, local, verbose=False):
    name = profile_name(profile)
    labels = {
        'installed': f'Patched ({name})',
        'restored': 'Unpatched',
        'unpatched': 'Unpatched',
        'prepared': 'The installation may not have finished.',
        'changed': f'Needs attention ({name}); installed files have changed.',
    }
    print(f'{profile["game"]} {profile["version"]}')
    print(f'Status: {labels.get(state["status"], "Unknown status. Use --verbose for details.")}')
    if state['status'] == 'installed':
        print('Original files are saved so you can restore them later.')
    elif state['status'] == 'restored':
        print('A backup copy is still saved.')
    elif state['status'] == 'prepared':
        print('Keep the backup. Check the game before trying to install again.')
    if verbose:
        print(f'Profile ID: {profile["id"]}')
        print(f'App location: {state["app"]}')
        print(f'Backup location: {local}')
        for kind in ('keyboard_mouse', 'trackpad'):
            print(f'{kind.replace("_", "/")} notes: {profile["validation"][kind]}')


def main():
    parser = argparse.ArgumentParser(
        description='Build and manage native keyboard and mouse input support for supported PlayCover games.',
        epilog='Examples:\n'
               '  python3 patch.py profiles\n'
               '  python3 patch.py apply --profile hsr\n'
               "  python3 patch.py status --app '/path/to/Honkai: Star Rail.app'\n"
               "  python3 patch.py restore --app '/path/to/Honkai: Star Rail.app'",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        'command', choices=['profiles', 'build', 'apply', 'install', 'update', 'restore', 'status'],
        help='profiles: list games; build: compile; apply/install: install a profile; update: rebuild and reapply it; restore: undo it; status: check it')
    parser.add_argument(
        '--profile',
        help='Profile name or ID (see profiles). Defaults to ZZZ; --app selects a matching regular profile automatically. Choose test profiles explicitly.')
    parser.add_argument(
        '--app', type=Path,
        help='Path to the game .app bundle (uses the standard PlayCover location if omitted)')
    parser.add_argument(
        '--json', action='store_true',
        help='Print status as JSON (only applies to the status command)')
    parser.add_argument(
        '--verbose', action='store_true',
        help='Show profile IDs, file locations and technical notes')
    args = parser.parse_args()
    if args.command == 'apply':
        args.command = 'install'
    if args.json and args.command != 'status':
        parser.error('--json can only be used with the status command')
    if args.command == 'profiles':
        print('Available profiles and apply commands:')
        profiles = [load_profile(path.stem) for path in (ROOT / 'profiles').glob('*.json')]
        profiles.sort(key=lambda item: (item['bundle_id'], item['version'], item.get('test_only', False)))
        for profile in profiles:
            label = ' (test profile — experimental)' if profile.get('test_only') else ' (regular profile)'
            short_name = profile_name(profile)
            print(f'- {profile["game"]} {profile["version"]}{label}')
            if args.verbose:
                print(f'  Profile ID: {profile["id"]}')
                print(f'  App ID: {profile["bundle_id"]}')
            print(f'  Apply: python3 patch.py apply --profile {short_name}')
        print("Add --app '/path/to/Game.app' if the game isn't in PlayCover's default location.")
        return
    app = args.app.expanduser().resolve() if args.app else None
    app_info = read_app_info(app) if app else None
    profile = (select_profile(app_info, args.profile)
               if app_info else load_profile(args.profile or DEFAULT_PROFILE))
    local = None
    app = (app or Path.home() / 'Library/Containers/io.playcover.PlayCover/Applications' /
           (profile['bundle_id'] + '.app')).expanduser().resolve()
    if args.command != 'build' and app_info is None:
        app_info = read_app_info(app)
        select_profile(app_info, profile['id'])
    detected = None
    detected_status = None
    if args.command in ('status', 'restore', 'update'):
        detected = applied_profile(app, app_info)
        if detected:
            active_profile, state, local, detected_status = detected
            if (args.command in ('restore', 'update') and args.profile is not None and
                    active_profile['id'] != profile['id']):
                raise RuntimeError(
                    f'{profile_name(active_profile)} is active, not {profile_name(profile)}. '
                    'Rerun without --profile and include --app to act on the active profile.')
            profile = active_profile
    if local is None:
        local = local_directory(profile)
    if args.command != 'status' and not args.json:
        print(f'{profile["game"]} {profile["version"]}')
        if profile.get('test_only'):
            print('This is an experimental test profile; some game features may not work as expected.')
        if args.verbose:
            print(f'Profile ID: {profile["id"]}')
            print(f'App location: {app}')
            print(f'Backup location: {local}')
    if args.verbose and args.command not in ('profiles', 'status'):
        for kind in ('keyboard_mouse', 'trackpad'):
            print(f'{kind.replace("_", "/")} notes: {profile["validation"][kind]}',
                  file=sys.stderr if args.json else sys.stdout)
    if args.command == 'build':
        build(profile)
    elif args.command == 'install':
        install(app, profile, local)
    elif args.command == 'status':
        if detected:
            state = dict(state, status=detected_status)
        else:
            require(digest(app / profile['framework_binary']) == profile['original_sha256']
                    and not (app / LIBRARY).exists(),
                    'The game has modified files but no saved patch information. Cannot determine patch status safely.')
            state = {'app': str(app), 'status': 'unpatched'}
        if args.json:
            print(json.dumps(state, indent=2))
        else:
            print_status(state, profile, local, args.verbose)
    elif args.command in ('restore', 'update') and detected is not None:
        require(detected_status == 'installed',
                'The saved install is incomplete or its files changed. No update or restore was made; run status --verbose for details.')
        if args.command == 'restore':
            restore(app, state, profile, local)
        else:
            update(app, state, profile, local)
    elif args.command in ('restore', 'update') and args.profile is None:
        raise RuntimeError('No patched profile is active for this game. Run status to check it.')
    else:
        state_path = local / 'state.json'
        require(state_path.exists(),
                f'No saved install was found for {profile_name(profile)}. Run status with --app to check which profile is active.')
        try:
            state = json.loads(state_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Couldn't read saved patch information at {state_path}: {error}") from error
        require(state.get('app') == str(app), 'The saved backup belongs to a different game app.')
        if args.command == 'restore':
            restore(app, state, profile, local)
        else:
            update(app, state, profile, local)


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        command = Path(error.cmd[0]).name if isinstance(error.cmd, (list, tuple)) else str(error.cmd)
        if command == 'codesign':
            message = f'macOS could not sign or verify the app (exit status {error.returncode}). See the signing output above.'
        elif command == 'sh':
            message = f'The bridge build failed (exit status {error.returncode}). See the build output above.'
        else:
            message = f"The required tool '{command}' stopped with exit status {error.returncode}. See the output above."
        print(f'Error: {message}', file=sys.stderr)
        raise SystemExit(1)
    except (RuntimeError, OSError) as error:
        print(f'Error: {error}', file=sys.stderr)
        raise SystemExit(1)
