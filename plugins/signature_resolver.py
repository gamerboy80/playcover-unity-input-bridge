"""Read-only discovery for reviewed plugin ABIs. Never uses reference addresses to find code."""
import copy
import hashlib
import json
from pathlib import Path

from profiles import require
from signatures import Image, HsrMethods, Metadata, resolve_functions

ROOT = Path(__file__).resolve().parents[1]


def resolve(binary, profile, contract_path, metadata=None):
    require(hashlib.sha256(binary).hexdigest() in profile['framework_sha256'],
            'Unsupported framework hash; a new build requires ABI and field review')
    contract = json.loads(Path(contract_path).read_text())
    require(contract['bundle_id'] == profile['bundle_id'], 'Signature contract identity mismatch')
    image = Image(binary)
    rules = contract['functions']
    managed = None
    if any('method' in rule for rule in rules.values()):
        require(metadata is not None, 'Managed signatures require game metadata')
        require(hashlib.sha256(metadata).hexdigest() == contract['metadata_sha256'],
                'Unsupported plugin metadata hash')
        if contract['metadata'] == 'hsr':
            wanted = {}
            for rule in rules.values():
                if 'method' in rule:
                    wanted.setdefault(rule['class'], set()).add(rule['method'])
            for rule in contract.get('types', {}).values():
                methods = wanted.setdefault(rule['class'], set())
                if 'method' in rule: methods.add(rule['method'])
            helper = json.loads((ROOT / 'signatures/com.HoYoverse.hkrpgoversea.json').read_text())
            managed = HsrMethods(image, metadata, helper['managed'], wanted)
        else:
            managed = Metadata(metadata)
    expected_bindings = {('entry', key) for key in profile['entries']} | {('method', key) for key in profile.get('methods', {})} | {('avatar_getter', key) for key in profile.get('avatar_getters', {})}
    if 'name_getter' in profile: expected_bindings.add(('name_getter', ''))
    require(set(contract['bindings']) == set(rules) and set(map(tuple, contract['bindings'].values())) == expected_bindings, 'Incomplete plugin signature bindings')
    addresses = resolve_functions(image, managed, rules)
    result = copy.deepcopy(profile)
    if contract.get("types"):
        require(isinstance(managed, HsrMethods), "Type discovery requires HSR metadata")
        result['types'] = {name: managed.type_index(rule, addresses) for name, rule in contract['types'].items()}
    for name, binding in contract['bindings'].items():
        address = addresses[name]
        kind, key = binding
        if kind == 'entry':
            entry = result['entries'][key]
            if isinstance(entry, list):
                entry[0] = hex(address)
            else:
                entry['address'] = hex(address)
        elif kind == 'method':
            result['methods'][key] = hex(address)
        elif kind == 'name_getter':
            result['name_getter']['address'] = hex(address)
        elif kind == 'avatar_getter':
            result['avatar_getters'][key]['address'] = hex(address)
        else:
            raise RuntimeError(f'Unknown plugin binding: {kind}')
    # Fields and the cave layout are an exact-build ABI, never inferred from a prologue.
    require(result == profile, 'Discovered bindings differ from the reviewed ABI; review before building')
    evidence = {'schema_version': 2, 'metadata_sha256': hashlib.sha256(metadata).hexdigest() if metadata is not None else None,
                'types': result.get('types', {}), 'framework_sha256': hashlib.sha256(binary).hexdigest(),
                'contract_sha256': hashlib.sha256(Path(contract_path).read_bytes()).hexdigest(),
                'functions': {key: hex(value) for key, value in addresses.items()},
                'validation': 'Static resolution only; runtime verification is separate'}
    return result, evidence


def resolve_app(app, profile, contract):
    from patch import applied_profile, check_installed, original_framework, read_app_info
    binary = app / 'Frameworks/UnityFramework.framework/UnityFramework'
    metadata = app / 'Data/Managed/Metadata/global-metadata.dat'
    require(all(path.resolve().is_relative_to(app.resolve()) for path in (binary, metadata)),
            'Framework or metadata points outside the app')
    data = binary.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    effective = copy.deepcopy(profile)
    input_profile = None
    if sha not in profile['framework_sha256']:
        active = applied_profile(app, read_app_info(app))
        require(active is not None and active[3] == 'installed', 'Unsupported framework hash; no verified input installation')
        installed, state, local, _ = active
        check_installed(app, state, installed)
        original = original_framework(app, installed, local)
        require(hashlib.sha256(original).hexdigest() in profile['framework_sha256'],
                'Input installation uses an unreviewed original plugin ABI')
        effective['framework_sha256'].append(sha)
        input_profile = installed['id']
    result, evidence = resolve(data, effective, contract, metadata.read_bytes())
    if input_profile: evidence['verified_input_profile'] = input_profile
    return result, evidence


def save_evidence(evidence, profile):
    """Keep generated discovery evidence with the main installer's local reports."""
    import re
    require(re.fullmatch(r'[A-Za-z0-9_.-]+', profile['bundle_id']), 'Invalid evidence identity')
    directory = ROOT / '.local/profiles/plugins'
    directory.mkdir(parents=True, exist_ok=True)
    require(directory.resolve().is_relative_to(ROOT.resolve()), 'Evidence directory points outside the workspace')
    name = f"{profile['bundle_id']}-{evidence['contract_sha256'][:12]}-{evidence['framework_sha256'][:12]}-v{evidence['schema_version']}.json"
    path = directory / name
    data = json.dumps(evidence, indent=2) + '\n'
    require(not path.is_symlink(), 'Existing plugin evidence is a symbolic link')
    if path.exists():
        require(path.read_text() == data, 'Existing plugin resolution evidence changed')
    else:
        with path.open('x') as stream:
            stream.write(data)
    return path.relative_to(ROOT)
