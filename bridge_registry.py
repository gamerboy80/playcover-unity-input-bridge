"""Shared ownership state for independently installed PlayCover bridge dylibs."""
import hashlib
import json
import os
import fcntl
import subprocess
from pathlib import Path
import tempfile

from macho import add_dylib, dylibs, executable_content, remove_dylib

OWNERS = {
    'native-input': '@executable_path/Frameworks/NativeInputBridge.dylib',
    'zzmi-metal': '@executable_path/Frameworks/ZZMIMetal.dylib',
}
SCHEMA_VERSION = 1


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _digest(path):
    return _sha256(path.read_bytes())


def _root(app, bundle_id, version):
    key = hashlib.sha256(str(app.resolve()).encode()).hexdigest()[:20]
    parent = app.resolve().parent / '.PlayCoverPatchRegistry'
    if parent.is_symlink():
        raise RuntimeError('The PlayCover bridge registry cannot be a symbolic link.')
    return parent / f'{bundle_id}-{version}' / key


def _lock(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise RuntimeError('The PlayCover bridge registry cannot be a symbolic link.')
    path = root / '.lock'
    if path.is_symlink():
        raise RuntimeError('The PlayCover bridge registry lock cannot be a symbolic link.')
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    return descriptor


def _signature_hashes(app):
    result = {}
    for directory in app.rglob('_CodeSignature'):
        if directory.is_symlink() or not directory.is_dir():
            continue
        for path in directory.rglob('*'):
            if path.is_symlink() or not path.is_file():
                raise RuntimeError(f'Unexpected code-signature resource: {path}')
            result[str(path.relative_to(app))] = _digest(path)
    return result


def _capture(app, main_relative):
    main = app / main_relative
    if main.is_symlink() or not main.is_file():
        raise RuntimeError(f'Game executable is missing or unsafe: {main_relative}')
    return {'main_sha256': _digest(main), 'signatures': _signature_hashes(app)}


def _save(registry):
    root = Path(registry['root'])
    if any(path.is_symlink() for path in (root.parent.parent, root.parent, root)):
        raise RuntimeError('The PlayCover bridge registry cannot contain symbolic links.')
    root.mkdir(parents=True, exist_ok=True)
    path = root / 'state.json'
    if path.is_symlink():
        raise RuntimeError('Bridge registry state cannot be a symbolic link.')
    fd, name = tempfile.mkstemp(prefix='.state-', dir=root)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump({key: value for key, value in registry.items() if key != 'root'},
                      output, indent=2)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _state_allowed(actual, state):
    candidates = [state['current']]
    if state.get('pending'):
        candidates.extend((state['pending']['previous'], state['pending']['planned']))
    for candidate in candidates:
        if actual == candidate:
            return True
    pending = state.get('pending')
    if not pending or actual.get('main_sha256') not in (
            pending['previous']['main_sha256'], pending['planned']['main_sha256']):
        return False
    before, after = pending['previous']['signatures'], pending['planned']['signatures']
    names = set(before) | set(after)
    return (set(actual['signatures']) <= names and
            all(actual['signatures'].get(name) in (before.get(name), after.get(name))
                for name in names))


def _refresh_resigned(app, actual, registry):
    previous = registry['current']
    if registry.get('pending') or actual['main_sha256'] == previous['main_sha256']:
        return False
    # Only the app seal may change; nested bundle signatures remain independently owned.
    nested = lambda state: {p: h for p, h in state['signatures'].items()
                            if p != '_CodeSignature/CodeResources'}
    if nested(actual) != nested(previous):
        return False
    if executable_content((app / registry['main_relative']).read_bytes()) != executable_content(
            compose(registry, registry['owners'])):
        return False
    # PlayCover can leave resource entries for removed plugins. Check signed code here;
    # installers retain their binary hash guards and re-seal resources in the staged app.
    result = subprocess.run(['/usr/bin/codesign', '--verify', '--strict', '--ignore-resources', str(app)],
                            capture_output=True)
    if result.returncode:
        return False
    descriptor = _lock(registry['root'])
    try:
        latest = json.loads((Path(registry['root']) / 'state.json').read_text(encoding='utf-8'))
        if (latest != {key: value for key, value in registry.items() if key != 'root'} or
                actual != _capture(app, registry['main_relative'])):
            raise RuntimeError('The app or bridge registry changed during signature validation. Retry the operation.')
        registry['current'] = actual
        _save(registry)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
    return True


def load(app, bundle_id, version, main_relative, create=True):
    app = Path(app).resolve()
    root = _root(app, bundle_id, version)
    if any(path.is_symlink() for path in (root.parent.parent, root.parent, root)):
        raise RuntimeError('The PlayCover bridge registry cannot contain symbolic links.')
    path = root / 'state.json'
    if path.is_symlink():
        raise RuntimeError('Bridge registry state cannot be a symbolic link.')
    if not path.exists() and not create:
        return None
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise RuntimeError('Bridge registry state is not a regular file.')
        if path.stat().st_size > 1024 * 1024:
            raise RuntimeError('Bridge registry state is too large to be valid.')
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f'Could not read bridge registry state: {error}') from error
        if (not isinstance(data, dict) or data.get('schema_version') != SCHEMA_VERSION or data.get('app') != str(app) or
                data.get('bundle_id') != bundle_id or data.get('version') != version or
                data.get('main_relative') != main_relative):
            raise RuntimeError('Bridge registry belongs to a different app build.')
        base = root / 'main.original'
        if (base.is_symlink() or not base.is_file() or
                _digest(base) != data.get('base_sha256')):
            raise RuntimeError('Bridge registry baseline is missing or changed.')
        data['root'] = str(root)
        actual = _capture(app, main_relative)
        if (not isinstance(data.get('owners'), dict) or
                any(owner not in OWNERS or load_path != OWNERS[owner]
                    for owner, load_path in data['owners'].items())):
            raise RuntimeError('Bridge registry contains an unknown bridge owner.')
        actual_owners = owners_in((app / main_relative).read_bytes())
        pending = data.get('pending')
        if pending:
            if (not isinstance(pending, dict) or not isinstance(pending.get('owners'), dict) or
                    any(owner not in OWNERS or load_path != OWNERS[owner]
                        for owner, load_path in pending['owners'].items()) or
                    actual_owners not in (data['owners'], pending['owners'])):
                raise RuntimeError('Bridge registry pending owners do not match the executable load commands.')
        elif actual_owners != data['owners']:
            raise RuntimeError('Bridge registry owners do not match the executable load commands.')
        signature_names = set(data.get('current', {}).get('signatures', {}))
        pending = data.get('pending') or {}
        signature_names.update(pending.get('previous', {}).get('signatures', {}))
        signature_names.update(pending.get('planned', {}).get('signatures', {}))
        if set(actual['signatures']) - signature_names:
            raise RuntimeError('Unrecognized signature resources were found.')
        if not _state_allowed(actual, data) and not _refresh_resigned(app, actual, data):
            raise RuntimeError('Game executable or signature changed outside a registered bridge install.')
        return data

    if (root / 'main.original').exists() or (root / 'main.original').is_symlink():
        raise RuntimeError('Bridge registry baseline exists without its state record.')
    current = bytearray((app / main_relative).read_bytes())
    owners = {}
    for owner, load_path in OWNERS.items():
        if any(name == load_path for _, name in dylibs(current)):
            owners[owner] = load_path
            remove_dylib(current, load_path)
    root.mkdir(parents=True, exist_ok=True)
    baseline = root / 'main.original'
    fd, name = tempfile.mkstemp(prefix='.main-', dir=root)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(current)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, baseline)
    finally:
        Path(name).unlink(missing_ok=True)
    state = {
        'schema_version': SCHEMA_VERSION,
        'app': str(app),
        'bundle_id': bundle_id,
        'version': version,
        'main_relative': main_relative,
        'base_sha256': _digest(baseline),
        'owners': owners,
        'current': _capture(app, main_relative),
        'root': str(root),
    }
    _save(state)
    return state


def owners_in(binary):
    names = {name for _, name in dylibs(binary)}
    return {owner: path for owner, path in OWNERS.items() if path in names}


def compose(registry, owners):
    root = Path(registry['root'])
    baseline = bytearray((root / 'main.original').read_bytes())
    for owner in sorted(owners):
        path = OWNERS.get(owner)
        if not path or owners[owner] != path:
            raise RuntimeError(f'Unknown or invalid bridge owner: {owner}')
        baseline = add_dylib(baseline, path)
    return baseline


def begin(registry, owners, staged_app):
    descriptor = _lock(registry['root'])
    try:
        path = Path(registry['root']) / 'state.json'
        latest = json.loads(path.read_text(encoding='utf-8'))
        if latest.get('pending'):
            raise RuntimeError('A bridge install was interrupted. Restore or retry it before starting another change.')
        if latest.get('current') != registry.get('current') or latest.get('owners') != registry.get('owners'):
            raise RuntimeError('Another bridge installer changed the app. Reload status and retry.')
        actual = _capture(Path(registry['app']), registry['main_relative'])
        if actual != registry['current']:
            raise RuntimeError('The app changed while the bridge was being staged. No files were changed.')
        planned = _capture(Path(staged_app), registry['main_relative'])
        registry['pending'] = {'owners': owners, 'previous': registry['current'], 'planned': planned}
        _save(registry)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def recover(registry, app):
    """Adopt the live side of an interrupted atomic bundle replacement."""
    descriptor = _lock(registry['root'])
    try:
        registry['owners'] = owners_in((Path(app) / registry['main_relative']).read_bytes())
        registry['current'] = _capture(Path(app), registry['main_relative'])
        registry.pop('pending', None)
        _save(registry)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def finish(registry, app):
    descriptor = _lock(registry['root'])
    try:
        latest = json.loads((Path(registry['root']) / 'state.json').read_text(encoding='utf-8'))
        pending = latest.get('pending')
        if not pending:
            raise RuntimeError('No bridge change is staged in the registry.')
        actual = _capture(Path(app), registry['main_relative'])
        if actual != pending['planned']:
            raise RuntimeError('Installed executable or signatures differ from the staged bridge build.')
        registry['owners'] = pending['owners']
        registry['current'] = actual
        registry.pop('pending', None)
        _save(registry)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
