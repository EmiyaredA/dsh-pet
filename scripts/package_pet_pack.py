#!/usr/bin/env python3
"""Package a Kurisu pet pack without raw videos, credentials or scratch files."""
import argparse
import json
import hashlib
from pathlib import Path
import zipfile
from pet_pack_manifest import validate_pack


def gap_record(action):
    attempt=(action.get('attempts') or [{}])[-1]
    return {'id':action['id'],'name':action['name'],'group':action.get('group'),
        'status':action['status'],'reason':(attempt.get('review') or {}).get('reason') or
            (action.get('quality_hold') or {}).get('reason') or
            attempt.get('processing_error') or '尚未生成'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-partial', action='store_true', help='Explicitly package the currently usable subset')
    args = parser.parse_args()
    root = args.pack.resolve()
    config = json.loads((root / 'pet/kurisu-config.json').read_text())
    library = json.loads((root / 'library.json').read_text()) if (root / 'library.json').exists() else None
    try:
        validate_pack(root, config, library, args.allow_partial)
    except ValueError as exc:
        parser.error(str(exc))
    approved={a['name']:a for a in (library or {}).get('actions',[]) if a['status']=='approved'}
    files = [root / n for n in ['README.md', 'preview.html', 'install.mjs', 'production.json',
             'references/kurisu-front.png', 'references/kurisu-front-safe.png',
             'references/kurisu-front-safe-blue.png', 'references/character-sheet.png']]
    for path in sorted((root/'pet').rglob('*')):
        if path.parent.name=='kurisu-animation' and library is not None:
            name=path.name.removesuffix('.report.json').removesuffix('.webm')
            if name not in approved:continue
            if path.suffix=='.webm' and hashlib.sha256(path.read_bytes()).hexdigest()!=approved[name]['sha256']:
                parser.error('Approved runtime hash changed: '+name)
        files.append(path)
    files += sorted((root / 'prompts').glob('*.txt'))
    files += sorted((root / 'prompts/library').glob('*.txt'))
    approved_ids={a['id'] for a in approved.values()}
    files += [p for p in sorted((root / 'previews/library').glob('*.png'))
              if library is None or p.stem in approved_ids]
    files += sorted((root / 'quality').rglob('*.json'))
    files += sorted((root / 'quality').rglob('*.md'))
    files += sorted((root / 'quality').rglob('*.png'))
    files += [p for p in [root / 'library.json', root / 'ACTIONS.md', root / 'GAPS.md', root / 'action-groups.json', root / 'action-directions.json'] if p.is_file()]
    if args.output.resolve().is_relative_to(root / 'pet'):
        parser.error('Archive output cannot be inside the runtime asset directory')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    delivery={'partial':args.allow_partial,'target_animation_count':106,
        'approved_animation_count':len(approved),'configured_animation_count':len(validate_pack(root,config,library,args.allow_partial)),
        'approved_ids':[a['id'] for a in approved.values()],
        'missing_ids':[a['id'] for a in (library or {}).get('actions',[]) if a['status']!='approved'],
        'missing_actions':[gap_record(a) for a in (library or {}).get('actions',[]) if a['status']!='approved'],
        'production_stage':(library or {}).get('stage'),
        'formal_full_config_promoted':len(approved)==106 and not args.allow_partial}
    with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            if path.is_file():
                if library is not None and path==root/'library.json':
                    archive.writestr('library.json',json.dumps(library,ensure_ascii=False,indent=2)+'\n')
                else:archive.write(path, path.relative_to(root))
        archive.writestr('DELIVERY.json',json.dumps(delivery,ensure_ascii=False,indent=2)+'\n')
    with zipfile.ZipFile(args.output) as archive:
        assert archive.testzip() is None
    print(args.output.resolve())


if __name__ == '__main__':
    main()
