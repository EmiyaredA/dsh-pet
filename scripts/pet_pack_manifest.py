"""Shared validation for every runtime animation pool and event slot."""
from pathlib import Path
import hashlib


def animation_slots(config):
    a = config['animations']
    names = []
    for key in ['idle', 'turn', 'drag', 'clicks']:
        names.extend(a[key])
    names.extend(x['name'] for x in a['moves']['actions'])
    for group in a['categories']:
        names.extend(group['actions'])
    for slots in a['events'].values():
        for slot in slots:
            names.extend(slot if isinstance(slot, list) else [slot])
    for name in names:
        if not isinstance(name, str) or not name or any(c in name for c in ['/', '\\', '\0']) or name in {'.', '..'}:
            raise ValueError(f'Invalid animation name: {name!r}')
    return names


def animation_names(config):
    return set(animation_slots(config))


def validate_pack(root: Path, config, library=None, allow_partial=False):
    names = animation_names(config)
    for name in names:
        path = root / 'pet/kurisu-animation' / (name + '.webm')
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f'Missing or empty animation: {name}')
    if library is not None and not allow_partial:
        actions = library['actions']
        if len(actions) != 106 or len({a['name'] for a in actions}) != 106:
            raise ValueError('Full library must contain 106 unique actions')
        if any(a['status'] != 'approved' for a in actions):
            raise ValueError('Full library is not completely approved; use --allow-partial for a labelled partial package')
        if names != {a['name'] for a in actions}:
            raise ValueError('Runtime pools do not match the approved 106-action library')
        if len(animation_slots(config)) != 106:
            raise ValueError('Every animation must occupy one distinct slot; repeated names cannot count toward 106')
        for key, count in [('balance', 6), ('whisper', 3), ('workStatus', 6)]:
            if len(config['animations']['events'][key]) != count:
                raise ValueError(f'Incorrect event slot count: {key}')
        for event, group in [('balance','余额'),('whisper','碎碎念'),('workStatus','工作状态')]:
            expected = [a['name'] for a in actions if a['group']==group]
            if config['animations']['events'][event] != expected:
                raise ValueError(f'Incorrect event slot order: {event}')
        hashes = set()
        for a in actions:
            path = root / 'pet/kurisu-animation' / (a['name']+'.webm')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in hashes or digest != a['sha256']:
                raise ValueError(f"Duplicate or altered animation: {a['id']}")
            hashes.add(digest)
        if {p.stem for p in (root/'pet/kurisu-animation').glob('*.webm')} != names:
            raise ValueError('Unexpected runtime animation files')
        weight = sum(config['animationWeights'].values()) + sum(c['weight'] for c in config['animations']['categories'])
        if weight != 100:
            raise ValueError('Animation weights must add up to 100')
    return names
