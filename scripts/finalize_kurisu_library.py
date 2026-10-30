#!/usr/bin/env python3
"""Prepare full config; promote only after all 106 independent clips pass review."""
import argparse
import hashlib
import json
from pathlib import Path
from pet_pack_manifest import animation_names, validate_pack

ROOT = Path(__file__).resolve().parents[1] / 'pet-packs/kurisu'


def full_config(current, groups):
    config = json.loads(json.dumps(current))
    for pet in config['pets']:
        pet.update(fixedEnabled=False, balanceEnabled=True, workStatusEnabled=True, whisperEnabled=False)
    config['animations'] = {
        'idle': groups['待机'], 'turn': groups['转向'], 'drag': groups['拖拽'], 'clicks': groups['点击回应'],
        'moves': {'default': {'minDist': 60, 'maxDist': 240, 'margin': 20, 'leadSec': 2, 'tailSec': 2},
                  'actions': [
                      {'name': groups['移动'][0]},
                      {'name': groups['移动'][1], 'params': {'minDist': 120, 'maxDist': 320}},
                      {'name': groups['移动'][2], 'params': {'minDist': 40, 'maxDist': 120}}]},
        'categories': [{'id': name, 'weight': weight, 'actions': groups[name]}
                       for name, weight in [('日常小动作',20), ('研究与玩耍',20), ('饮食',16), ('时节',14), ('吐槽与思考',10)]],
        'events': {'balance': groups['余额'], 'whisper': groups['碎碎念'], 'workStatus': groups['工作状态']}}
    config['animationWeights'] = {'idle': 10, 'turn': 5, 'move': 5}
    assert len(animation_names(config)) == 106
    assert sum(x['weight'] for x in config['animations']['categories']) + sum(config['animationWeights'].values()) == 100
    return config


def validate_media(root, config, library):
    names = validate_pack(root, config, library)
    hashes = set()
    for a in library['actions']:
        path = root / 'pet/kurisu-animation' / (a['name'] + '.webm')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != a['sha256'] or digest in hashes:
            raise ValueError(f"Altered or duplicate clip: {a['id']}")
        hashes.add(digest)
        report = json.loads(path.with_suffix('.report.json').read_text())
        v = report['verification']
        if (v['width'], v['height'], v['fps'], v['frames'], v['alpha_min'], v['alpha_max']) != (640,360,24,240,0,255):
            raise ValueError(f"Media check failed: {a['id']}")
        if not a.get('reused') and a['attempts'][-1].get('review',{}).get('verdict') != 'pass':
            raise ValueError(f"Missing visual review: {a['id']}")
    if {p.stem for p in (root / 'pet/kurisu-animation').glob('*.webm')} != names:
        raise ValueError('Unexpected runtime clips')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--promote', action='store_true')
    args = p.parse_args()
    current = json.loads((ROOT / 'pet/kurisu-config.json').read_text())
    config = full_config(current, json.loads((ROOT / 'action-groups.json').read_text()))
    target = ROOT / 'kurisu-config.full.json'
    target.write_text(json.dumps(config, ensure_ascii=False, indent=2)+'\n')
    if args.promote:
        library = json.loads((ROOT / 'library.json').read_text())
        validate_media(ROOT, config, library)
        destination = ROOT / 'pet/kurisu-config.json'
        temporary = destination.with_suffix('.next.json')
        temporary.write_text(target.read_text()); temporary.replace(destination)
    print(json.dumps({'staged_config': str(target), 'promoted': args.promote, 'unique_actions':106}))


if __name__ == '__main__':
    main()
