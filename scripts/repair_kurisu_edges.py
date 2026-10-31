#!/usr/bin/env python3
"""Prepare auditable, zero-generation-call RGBA edge revisions.

Outputs candidates first. --apply atomically publishes an inspected candidate
only when its source hash still matches the live ledger, preserving old media.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import numpy as np
import cv2
from build_pet_pack import read_frame,verify_output
from kurisu_hair_matte import clear_hair_islands,despill_boundary
from kurisu_library import ROOT,PACK,load,save,now,production_lock,write_alpha_contact

VERSION='hair_islands_and_boundary_despill_v5'
ALGORITHM_SHA=hashlib.sha256((ROOT/'scripts/kurisu_hair_matte.py').read_bytes()).hexdigest()


def prepare(action,source_override=None):
    source=PACK/action['file'];before=hashlib.sha256(source.read_bytes()).hexdigest()
    assert before==action['sha256']
    # Rebuild a newer edge algorithm from its pre-repair original, never from
    # an already color-modified version. Preserve all earlier non-edge edits.
    revisions=action.get('media_revisions',[])
    for revision in reversed(revisions):
        if '/edge-repair/' not in revision.get('candidate',''):break
        source=PACK/revision['archive_file']
    if source_override is not None:source=Path(source_override)
    folder=ROOT/'temp/kurisu/edge-repair'/action['id']/before[:12]/VERSION
    folder.mkdir(parents=True,exist_ok=True)
    output=folder/source.name
    marker=output.with_suffix('.edge.json')
    if marker.exists():
        cached=json.loads(marker.read_text())
        if cached.get('algorithm_sha256')==ALGORITHM_SHA:return cached
    decoder=subprocess.Popen(['ffmpeg','-v','error','-c:v','libvpx-vp9','-i',str(source),'-f','rawvideo','-pix_fmt','rgba','-'],stdout=subprocess.PIPE)
    encoder=subprocess.Popen(['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgba','-s','640x360','-r','24','-i','-',
        '-an','-c:v','libvpx-vp9','-pix_fmt','yuva420p','-lossless','1','-auto-alt-ref','0','-b:v','0','-crf','0','-row-mt','1','-threads','4','-cpu-used','4',str(output)],stdin=subprocess.PIPE)
    samples=[];frames=0
    try:
        while data:=read_frame(decoder.stdout,640*360*4):
            rgba=np.frombuffer(data,np.uint8).reshape(360,640,4)
            fixed,white=clear_hair_islands(rgba)
            fixed,green=despill_boundary(fixed)
            encoder.stdin.write(fixed.tobytes())
            samples.append({'frame':frames,'white_island_pixels':white,'despilled_pixels':green});frames+=1
    finally:
        decoder.stdout.close();encoder.stdin.close()
        dr=decoder.wait();er=encoder.wait()
    assert dr==er==0 and frames==240
    verification=verify_output(output,shutil.which('ffmpeg'),shutil.which('ffprobe'))
    report_path=source.with_suffix('.report.json')
    report=json.loads(report_path.read_text()) if report_path.exists() else {}
    report.update({'output':output.name,'verification':verification,'encoding_lossless':True,
        'edge_revision':{'method':VERSION,'source_sha256':before,'new_model_calls':0}})
    output.with_suffix('.report.json').write_text(json.dumps(report,indent=2)+'\n')
    record={'action':action['id'],'method':VERSION,'algorithm_sha256':ALGORITHM_SHA,'source_sha256':before,'repair_input':str(source),'candidate':str(output),'candidate_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
        'prepared_at':now(),'new_model_calls':0,'samples':samples,'report':report}
    marker.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({k:v for k,v in record.items() if k not in {'samples','report'}},ensure_ascii=False),flush=True)
    return record


def apply(record):
    with production_lock():
        state=load();a=next(a for a in state['actions'] if a['id']==record['action'])
        assert a['status'] in {'approved','awaiting_local_repair'} and a['sha256']==record['source_sha256']
        source=Path(record['candidate']);assert hashlib.sha256(source.read_bytes()).hexdigest()==record['candidate_sha256']
        target=PACK/a['file'];archive=PACK/'source/library/media-revisions'/a['id']/a['sha256'][:16]
        archive.mkdir(parents=True,exist_ok=True)
        for path in [target,target.with_suffix('.report.json')]:
            if path.exists():shutil.copy2(path,archive/path.name)
        entry={k:v for k,v in record.items() if k not in {'samples','report'}}
        entry.update({'archive_file':str((archive/target.name).relative_to(PACK)),'applied_at':now(),
            'reason':'User reported enclosed white hair gaps and green silhouette spill; preserve eyes, costume whites, pose and timing'})
        a.setdefault('media_revisions',[]).append(entry)
        staged=target.with_suffix('.next.webm');shutil.copy2(source,staged);staged.replace(target)
        shutil.copy2(source.with_suffix('.report.json'),target.with_suffix('.report.json'))
        a['sha256']=record['candidate_sha256']
        if a['status']=='awaiting_local_repair':
            a['status']='approved'
            a.setdefault('resolved_quality_holds',[]).append(a.pop('quality_hold',{}))
        if record.get('motion_mode'):a['motion_mode']=record['motion_mode']
        if a['attempts']:
            a['attempts'][-1]['edge_revision']=entry
            a['attempts'][-1]['report']=record['report']
            write_alpha_contact(a,a['attempts'][-1],target)
        subprocess.run(['ffmpeg','-y','-v','error','-c:v','libvpx-vp9','-i',str(target),'-frames:v','1',str(PACK/a['poster'])],check=True)
        # Delivery artifacts refer to the older hash until explicitly republished.
        for key in ['delivery_asset_id','delivery_node_id','delivery_upload_started']:
            if key in a:a['media_revisions'][-1][key]=a.pop(key)
        save(state)
    print('Applied '+a['id']+'; zero new model calls',flush=True)


if __name__=='__main__':
    cv2.setNumThreads(1)
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--action',action='append',required=True);p.add_argument('--apply',action='store_true')
    args=p.parse_args();state=load()
    for aid in args.action:
        a=next(a for a in state['actions'] if a['id']==aid);assert a['status']=='approved'
        record=prepare(a)
        if args.apply:apply(record)
