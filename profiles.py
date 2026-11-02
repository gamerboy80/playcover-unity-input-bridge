"""Load reviewed game profiles and generate constants for the shared bridge."""
import json
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parent
DEFAULT_PROFILE = 'com.HoYoverse.Nap-3.3.0'
PROFILE_ALIASES = {'zzz-3.3.0': DEFAULT_PROFILE, 'hsr': 'com.HoYoverse.hkrpgoversea-4.6.0'}
ADDRESS_NAMES = {
    'Statics', 'NewString', 'AddDevice', 'MouseMakeCurrent', 'NativeTime',
    'QueueInputEvent', 'ScreenWidth', 'ScreenHeight', 'CursorLock', 'CursorVisible',
    'ReadVector2', 'EnableMouseProcessing',
}
FIELD_NAMES = {
    'StaticInputManager', 'StaticKeyboard', 'StaticMouse', 'DeviceID',
    'StateBlock', 'MousePosition', 'MouseDelta', 'MouseScroll',
}
LEGACY_ADDRESSES = {'UIScrollReturn','ScreenWidth','ScreenHeight','CursorLock','CursorVisible','FrameCount',
    'KeySlot','KeyDownSlot','KeyUpSlot','AnyKeySlot','AnyKeyDownSlot','MousePositionSlot','MouseScrollSlot','MouseButtonSlot',
    'MouseButtonDownSlot','MouseButtonUpSlot','AxisSlot','AxisRawSlot','LegacyMousePresentSlot'}

OPTIONAL_ADDRESSES = {'GetMouseProcessing', 'MouseProcessingEnabled', 'ReadProcessedScroll',
                      'LegacyMousePresent', 'LegacyMousePresentSlot'}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def hex_number(value):
    require(isinstance(value, str) and re.fullmatch(r'0x[0-9a-fA-F]+', value),
            f'Expected a hexadecimal string, got {value!r}')
    result = int(value, 16)
    require(result < 2**64, 'Address/offset exceeds 64 bits')
    return result


def validate(data, profile_id):
    require(data['schema_version'] == 1, 'Unsupported profile schema')
    require(data['id'] == profile_id, 'Profile ID must match its filename')
    for key in ('game', 'version', 'bundle_id', 'executable'):
        require(isinstance(data[key], str) and data[key] and
                not any(ord(c) < 32 for c in data[key]), f'Invalid {key}')
    require(re.fullmatch(r'[A-Za-z0-9_.-]+', data['bundle_id']), 'Invalid bundle ID')
    require(data['executable'] not in ('.', '..') and '/' not in data['executable'],
            'Executable must be a bundle-root filename')
    require(data['architecture'] == 'arm64', 'Only arm64 Catalyst is implemented')
    binary = PurePosixPath(data['framework_binary'])
    require(not binary.is_absolute() and '..' not in binary.parts and
            len(binary.parts) == 3 and binary.parts[0] == 'Frameworks' and
            binary.parts[1].endswith('.framework') and
            binary.parts[2] == binary.parts[1][:-10], 'Invalid framework binary path')
    require(re.fullmatch(r'[0-9a-f]{64}', data['original_sha256']), 'Invalid original SHA-256')
    ranges = []
    names = set()
    require(isinstance(data['patches'], list), 'Patches must be a list')
    for patch in data['patches']:
        require(patch['name'] and patch['name'] not in names and patch['reason'],
                'Patches need unique names and reasons')
        names.add(patch['name'])
        offset = hex_number(patch['file_offset'])
        for key in ('expected', 'replacement'):
            require(isinstance(patch[key], str) and
                    re.fullmatch(r'(?:[0-9a-fA-F]{2})+', patch[key]), 'Invalid patch bytes')
        expected, replacement = bytes.fromhex(patch['expected']), bytes.fromhex(patch['replacement'])
        require(len(expected) == len(replacement), 'Patch must preserve binary length')
        require(offset % 4 == 0 and len(expected) % 4 == 0, 'Unaligned arm64 instruction patch')
        ranges.append((offset, offset + len(expected)))
    ranges.sort()
    require(all(a[1] <= b[0] for a, b in zip(ranges, ranges[1:])), 'Overlapping patches')
    bridge = data['bridge']
    require(bridge['backend'] in ('unity-input-system-v1','unity-legacy-v1'), 'Unsupported bridge backend')
    legacy = bridge['backend'] == 'unity-legacy-v1'
    if legacy:
        require(type(bridge.get('scroll_units_per_step')) is int and
                1 <= bridge['scroll_units_per_step'] <= 1200, 'Invalid legacy scroll units per step')
    require(bridge['image_suffix'] == '/' + '/'.join(binary.parts[1:]), 'Image suffix mismatch')
    require(type(bridge['mouse_state_bytes']) is int and 30 <= bridge['mouse_state_bytes'] <= 64,
            'Mouse payload must fit the supported layout')
    for group, expected_names in (('addresses', LEGACY_ADDRESSES if legacy else ADDRESS_NAMES),
                                  ('fields', set() if legacy else FIELD_NAMES)):
        names = set(bridge[group])
        allowed = expected_names | (OPTIONAL_ADDRESSES if group == 'addresses' else set())
        require(expected_names <= names <= allowed, f'Unexpected/missing bridge {group}')
        for name, value in bridge[group].items():
            number = hex_number(value)
            require(number > 0 or name == 'EnableMouseProcessing' or name in OPTIONAL_ADDRESSES, f'Zero {name}')
            if group == 'addresses':
                require(number % 4 == 0, f'Unaligned address: {name}')
                if name.endswith('Slot'):
                    require(number % 8 == 0, 'Unaligned mouse presence callback slot')
    require(all(isinstance(data['validation'][key], str) and data['validation'][key]
                for key in ('keyboard_mouse', 'trackpad', 'evidence')), 'Missing validation notes')
    return data


def load_profile(profile_id=DEFAULT_PROFILE):
    profile_id = PROFILE_ALIASES.get(profile_id, profile_id)
    require(isinstance(profile_id, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', profile_id),
            'Invalid profile ID')
    try:
        return validate(json.loads((ROOT / 'profiles' / (profile_id + '.json')).read_text()), profile_id)
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(f'Invalid profile {profile_id}: {error}') from error


def match_app(profile, info):
    return all(info.get(key) == profile[field] for key, field in (
        ('CFBundleIdentifier', 'bundle_id'), ('CFBundleShortVersionString', 'version'),
        ('CFBundleExecutable', 'executable')))


def select_profile(info, profile_id=None):
    if profile_id:
        profile = load_profile(profile_id)
        require(match_app(profile, info),
                f"App identity/version does not match profile {profile['id']}")
        return profile
    matches = [p for p in (load_profile(path.stem) for path in sorted((ROOT / 'profiles').glob('*.json')))
               if match_app(p, info)]
    identity = f"{info.get('CFBundleIdentifier', '?')} {info.get('CFBundleShortVersionString', '?')}"
    require(matches, f'No matching profile for {identity}; supported builds: ' +
            ', '.join(path.stem for path in sorted((ROOT / 'profiles').glob('*.json'))))
    require(len(matches) == 1, f'Ambiguous profiles for {identity}; select --profile explicitly')
    return matches[0]


def instruction_patches(profile):
    return [(hex_number(p['file_offset']), bytes.fromhex(p['expected']), bytes.fromhex(p['replacement']))
            for p in profile['patches']]


def generate_header(profile):
    bridge = profile['bridge']
    lines = ['// Generated from profiles/' + profile['id'] + '.json; do not edit.', '#pragma once']
    for name, value in (('ProfileID', profile['id']), ('BundleID', profile['bundle_id']),
                        ('Version', profile['version']), ('ImageSuffix', bridge['image_suffix'])):
        lines.append(f'#define Game{name} {json.dumps(value)}')
    lines.append(f'#define GameLegacyBackend {int(bridge["backend"] == "unity-legacy-v1")}')
    lines.append(f'#define GameMouseStateBytes {bridge["mouse_state_bytes"]}')
    if bridge['backend'] == 'unity-legacy-v1':
        lines.append(f'#define GameLegacyScrollUnitsPerStep {bridge["scroll_units_per_step"]}')
    for group, prefix in (('addresses', 'Game'), ('fields', 'GameField')):
        values = dict(bridge[group])
        if group == 'addresses':
            values = {**dict.fromkeys(OPTIONAL_ADDRESSES, '0x0'), **values}
        for name, value in sorted(values.items()):
            lines.append(f'#define {prefix}{name} {hex_number(value):#x}ULL')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    try:
        profile = load_profile(sys.argv[1])
        Path(sys.argv[2]).write_text(generate_header(profile))
    except (RuntimeError, OSError, IndexError) as error:
        raise SystemExit(str(error))
