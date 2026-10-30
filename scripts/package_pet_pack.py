#!/usr/bin/env python3
"""Package a Kurisu pet pack without raw videos, credentials or scratch files."""
import argparse
import json
from pathlib import Path
import zipfile
from pet_pack_manifest import validate_pack


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
    files = [root / n for n in ['README.md', 'preview.html', 'install.mjs', 'production.json',
             'references/kurisu-front.png', 'references/kurisu-front-safe.png', 'references/character-sheet.png']]
    files += sorted((root / 'pet').rglob('*'))
    files += sorted((root / 'prompts').glob('*.txt'))
    files += sorted((root / 'prompts/library').glob('*.txt'))
    files += sorted((root / 'previews/library').glob('*.png'))
    files += sorted((root / 'quality').glob('*.json'))
    files += [p for p in [root / 'library.json', root / 'ACTIONS.md', root / 'action-groups.json', root / 'action-directions.json'] if p.is_file()]
    if args.output.resolve().is_relative_to(root / 'pet'):
        parser.error('Archive output cannot be inside the runtime asset directory')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            if path.is_file():
                archive.write(path, path.relative_to(root))
    with zipfile.ZipFile(args.output) as archive:
        assert archive.testzip() is None
    print(args.output.resolve())


if __name__ == '__main__':
    main()
