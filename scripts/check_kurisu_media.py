#!/usr/bin/env python3
"""Decode every frame of each accepted clip; cache audit by SHA256."""
import hashlib
import json
from pathlib import Path
import shutil
from datetime import datetime, timezone
from build_pet_pack import verify_output

ROOT=Path(__file__).resolve().parents[1]/'pet-packs/kurisu'


def main():
    state=json.loads((ROOT/'library.json').read_text())
    path=ROOT/'quality/media-audit.json';path.parent.mkdir(exist_ok=True)
    audit=json.loads(path.read_text()) if path.exists() else {'schema_version':1,'clips':{}}
    for a in state['actions']:
        if a['status']!='approved':continue
        file=ROOT/a['file'];digest=hashlib.sha256(file.read_bytes()).hexdigest()
        assert digest==a['sha256'],f"Changed clip: {a['id']}"
        previous=audit['clips'].get(a['id'],{})
        if previous.get('sha256')==digest and previous.get('verifier_version')==3:continue
        verification=verify_output(file,shutil.which('ffmpeg'),shutil.which('ffprobe'))
        audit['clips'][a['id']]={'sha256':digest,'file':a['file'],'verification':verification,'verifier_version':3,
                                 'verified_at':datetime.now(timezone.utc).isoformat()}
        temp=path.with_suffix('.next.json');temp.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');temp.replace(path)
        print(a['id']+' all frames verified',flush=True)
    approved=[a['id'] for a in state['actions'] if a['status']=='approved']
    audit['current_approved_ids']=approved
    path.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    print(f"Audited {len(approved)} currently accepted clips; withdrawn hashes retained as history")


if __name__=='__main__':main()
