#!/usr/bin/env python3
"""Build headers or stage an isolated, exact-build ZZZ damage-probe app."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from macho import _commands
from patch import clone_app, closed, digest, read_app_info, require, run
from plugins.veritas.stage import address_in_x16, words
from signatures import Image

PROFILE = json.loads(Path(__file__).with_name('zzz-3.3.1.json').read_text())
FRAMEWORK = Path('Frameworks/UnityFramework.framework')
PLUGIN = 'ZZZDamageProbe.dylib'


def detours(profile=PROFILE):
    for index, (name, entry) in enumerate(profile['entries'].items()):
        address = int(entry['address'], 16)
        expected = bytes.fromhex(entry['expected'])
        stub = int(profile['code_padding'], 16) + index * 48
        slot = int(profile['data_padding'], 16) + index * 8
        require(address % 4 == stub % 4 == slot % 8 == 0 and len(expected) == 12,
                'Unaligned or unsupported detour')
        jump = address_in_x16(address, stub) + words(0xd61f0200)
        require(jump == bytes.fromhex(entry['replacement']), 'Recorded replacement does not match the detour')
        # Empty callback slots execute the original instructions without the plugin.
        code = (address_in_x16(stub, slot) + words(0xc8dffe10, 0xb4000050, 0xd61f0200) +
                expected + address_in_x16(stub + 32, address + 12) + words(0xd61f0200))
        yield name, address, expected, jump, stub, slot, code


def write_header(path):
    lines = ['/* Generated from the reviewed ZZZ probe profile. */']
    uuid = ', '.join(f'0x{byte:02x}' for byte in bytes.fromhex(PROFILE['uuid']))
    lines.append(f'static const uint8_t ProbeUUID[] = {{{uuid}}};')
    for name, entry, expected, jump, stub, slot, code in detours():
        for label, address in [('Entry', entry), ('Original', stub + 20), ('Slot', slot), ('Stub', stub)]:
            lines.append(f'#define Probe{name}{label} 0x{address:x}')
        for label, data in [('Jump', jump), ('Code', code)]:
            values = ', '.join(f'0x{byte:02x}' for byte in data)
            lines.append(f'static const uint8_t Probe{name}{label}[] = {{{values}}};')
    for name, offset in PROFILE['fields'].items():
        lines.append(f'#define Probe{name} {offset}')
    for name, getter in {'ObjectName': PROFILE['name_getter'], **PROFILE['avatar_getters']}.items():
        lines.append(f"#define Probe{name} {getter['address']}")
        expected = ', '.join(f'0x{b:02x}' for b in bytes.fromhex(getter['expected']))
        lines.append(f'static const uint8_t Probe{name}Code[] = {{{expected}}};')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines) + '\n')


def instrument(binary, profile=PROFILE):
    require(hashlib.sha256(binary).hexdigest() in profile['framework_sha256'],
            'Unsupported ZZZ framework hash')
    data = bytearray(binary)
    image = Image(data)
    if getter := profile.get('name_getter'):
        expected = bytes.fromhex(getter['expected'])
        require(image.body(int(getter['address'], 16)).startswith(expected),
                'Unity object-name getter changed')
    for name, getter in profile.get('avatar_getters', {}).items():
        require(image.body(int(getter['address'], 16)).startswith(bytes.fromhex(getter['expected'])),
                f'{name} getter changed')
    require(next(vm for name, vm, _, _, _ in image.segments if name == '__TEXT') == 0,
            'Unexpected preferred image base')
    uuids = [data[pos + 8:pos + 24].hex() for pos, cmd, _ in _commands(data)[0] if cmd == 0x1b]
    require(uuids == [profile['uuid']], 'Unexpected framework UUID')
    edits, reserved = [], []
    for name, entry, expected, jump, stub, slot, code in detours(profile):
        require(entry in image.function_set and len(image.body(entry)) >= len(expected),
                f'{name} is not a suitable function entry')
        require(any(segment == '__DATA' and vm + stored <= slot and slot + 8 <= vm + size
                    for segment, vm, size, _, stored in image.segments),
                f'{name} callback is outside zero-filled writable storage')
        for segment, address, length in [('__TEXT', stub, len(code)), ('__DATA', slot, 8)]:
            require(all(s != segment or address + length <= start or start + size <= address
                        for (s, _), (start, size, _) in image.sections.items()),
                    f'{name} overlaps a game section')
        for address, length in [(entry, len(jump)), (stub, len(code)), (slot, 8)]:
            require(all(address + length <= start or start + size <= address for start, size in reserved),
                    'Overlapping probe edits')
            reserved.append((address, length))
        source, target = image.file(entry, 12, '__TEXT'), image.file(stub, len(code), '__TEXT')
        require(data[source:source + 12] == expected, f'{name} entry changed')
        require(not any(data[target:target + len(code)]), f'{name} padding is in use')
        edits.extend([(source, jump), (target, code)])
    for offset, replacement in edits:
        data[offset:offset + len(replacement)] = replacement
    return data


def cleanup_previews(output, source_app):
    directory = ROOT / 'build/plugins'
    if output.parent != directory:
        return
    closed(PROFILE)
    for plan in sorted(directory.glob('ZZZ-Damage-*.plan.json')):
        app = directory / (plan.name.removesuffix('.plan.json') + '.app')
        if app in (output, source_app) or app.is_symlink() or plan.is_symlink() or not app.is_dir():
            continue
        try:
            record = json.loads(plan.read_text())
            info = read_app_info(app)
            require(isinstance(record, dict) and isinstance(info, dict), 'Invalid preview record')
            files = {
                app / FRAMEWORK / 'UnityFramework': 'signed_framework_sha256',
                app / PROFILE['executable']: 'signed_executable_sha256',
                app / 'Frameworks/UserPlugins' / PLUGIN: 'plugin_sha256',
            }
            require(record.get('status') == 'signed' and info.get('CFBundleIdentifier') == PROFILE['bundle_id'],
                    'Unrecognized preview')
            require(all(path.resolve().is_relative_to(app) and digest(path) == record.get(key)
                        for path, key in files.items()), 'Preview files changed')
        except (OSError, RuntimeError, ValueError):
            print(f'Kept unverified preview: {app.name}')
            continue
        shutil.rmtree(app)
        plan.unlink()
        print(f'Removed old preview: {app.name}')


def stage(app, output):
    info = read_app_info(app)
    require(all(str(info.get(key)) == PROFILE[field] for key, field in [
        ('CFBundleIdentifier', 'bundle_id'), ('CFBundleShortVersionString', 'version'),
        ('CFBundleVersion', 'build'), ('CFBundleExecutable', 'executable')]),
        'This probe requires the reviewed ZZZ 3.3.1 build 4')
    require(output.suffix == '.app' and not output.exists() and app not in output.parents and output != app,
            'Choose a new .app output outside the source app')
    closed(PROFILE)
    source = app / FRAMEWORK / 'UnityFramework'
    require(source.resolve().is_relative_to(app), 'Framework points outside the source app')
    require(digest(app / 'Data/Managed/Metadata/global-metadata.dat') == PROFILE['metadata_sha256'],
            'Unsupported ZZZ metadata hash')
    plugin = ROOT / 'build/plugins' / PLUGIN
    require(plugin.is_file(), 'Build the probe first with sh plugins/zzz_damage/build.sh')
    original = source.read_bytes()
    patched = instrument(original)
    output.parent.mkdir(parents=True, exist_ok=True)
    plan = output.with_suffix('.plan.json')
    require(not plan.exists(), 'A probe plan already exists at this output path')
    record = {'source_framework_sha256': hashlib.sha256(original).hexdigest(),
              'planned_unsigned_framework_sha256': hashlib.sha256(patched).hexdigest(),
              'plugin_sha256': digest(plugin), 'status': 'prepared'}
    plan.write_text(json.dumps(record, indent=2) + '\n')
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        clone_app(app, staged)
        binary = staged / FRAMEWORK / 'UnityFramework'
        target = staged / 'Frameworks/UserPlugins' / PLUGIN
        require(all(path.resolve().is_relative_to(staged) for path in [binary, target]),
                'Framework or plugin directory points outside the staged copy')
        require(not target.is_symlink(), 'Probe destination is a symbolic link')
        require(digest(binary) == record['source_framework_sha256'], 'Source changed while cloning')
        binary.write_bytes(patched)
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(plugin, target)
        run('/usr/bin/codesign', '--force', '--sign', '-', '--preserve-metadata=entitlements', str(staged / FRAMEWORK))
        run('/usr/bin/codesign', '--force', '--sign', '-', '--preserve-metadata=entitlements', str(staged))
        run('/usr/bin/codesign', '--verify', '--strict', str(target))
        run('/usr/bin/codesign', '--verify', '--strict', str(staged))
        record.update(status='signed', signed_framework_sha256=digest(binary),
                      signed_executable_sha256=digest(staged / PROFILE['executable']))
        plan.write_text(json.dumps(record, indent=2) + '\n')
        require(digest(source) == record['source_framework_sha256'], 'Source app changed during staging')
        staged.rename(output)
    print(f'Prepared diagnostic copy: {output}')
    cleanup_previews(output, app)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--header', type=Path)
    parser.add_argument('--app', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.header and not (args.app or args.output):
        write_header(args.header)
    elif args.app and args.output and not args.header:
        stage(args.app.resolve(), args.output.resolve())
    else:
        parser.error('Use --header, or --app and --output')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f'ZZZ damage probe: {error}')
