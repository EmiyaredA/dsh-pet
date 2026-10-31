#!/usr/bin/env python3
"""Detached, reviewed GREEN-source processing. Never writes the production ledger.

Download -> source hash/background scan -> independent source-review gate ->
bounded whole-frame palette fit -> green-only matte -> lossless VP9 Alpha.
The queue alone claims/CAS-commits work; the operator alone approves media.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import math
from fractions import Fraction
import subprocess
import sys
import cv2
import numpy as np
from build_pet_pack import convert,key_green
from repair_kurisu_palette import estimate_track,transform_rgb,neutral_only,canonical_palette_anchor,compose_palette_track
from kurisu_source_qa import load_source_review,source_review_path,ALLOW
from green_edge_despill import despill_auburn_collar
from kurisu_palette_anchor import select_palette_anchor
from kurisu_background import scan_source_background

ROOT=Path(__file__).resolve().parents[1]
PACK=ROOT/'pet-packs/kurisu'
WORKER_VERSION='green_only_canonical_palette_and_edge_v3'
WAN_MODEL_ID='b217e3cd-884d-4015-a3fa-98ab7608a67e'
WAN_MODEL_SLUG='wan2.2animate-v4-motion_retargeting'
WAN_PROFILE='wan_normal_green_key_no_palette'
WAN_WORKER_VERSION='wan_normal_green_key_no_palette_v1'
BLUE_SOURCE_WORKER_VERSION='blue_source_recovery_only_v1'
U24_MODEL_ID='418c676d-1a59-4b3e-a716-b99de8038c71'
U24_MODEL_SLUG='minimax_h3_zm_u24'
U24_PROFILE='h3_u24_normal_green_key_no_palette'
U24_WORKER_VERSION='h3_u24_normal_green_key_no_palette_v1'


def processing_profile(attempt):
    profile=attempt.get('processing_profile')
    if profile is None:return 'h3_bounded_palette'
    identities={WAN_PROFILE:(WAN_MODEL_ID,WAN_MODEL_SLUG),U24_PROFILE:(U24_MODEL_ID,U24_MODEL_SLUG)}
    if not isinstance(profile,str) or profile not in identities or (attempt.get('model_id'),attempt.get('model_slug'))!=identities[profile]:
        raise ValueError('Unsupported or mismatched explicit processing profile/model')
    return profile


def require_ten_seconds_video(source,ffprobe='ffprobe',*,source_label='Wan'):
    """Video timing only; a long audio track must never pad a short video."""
    data=json.loads(subprocess.check_output([ffprobe,'-v','error','-show_entries',
        'stream=codec_type,duration,duration_ts,time_base,avg_frame_rate,nb_frames:format=duration',
        '-of','json',str(source)]))
    videos=[x for x in data.get('streams',[]) if x.get('codec_type')=='video']
    if len(videos)!=1:raise ValueError(f'Expected exactly one video stream for {source_label} source timing')
    v=videos[0];seconds=None;basis=None
    def finite(value):
        try:x=float(value)
        except (TypeError,ValueError):return None
        return x if math.isfinite(x) and x>0 else None
    seconds=finite(v.get('duration'));basis='video_stream_duration'
    if seconds is None:
        try:seconds=finite(float(Fraction(v['time_base']))*int(v['duration_ts']));basis='video_duration_ts_time_base'
        except (KeyError,TypeError,ValueError,ZeroDivisionError):pass
    if seconds is None:
        try:seconds=finite(int(v['nb_frames'])/float(Fraction(v['avg_frame_rate'])));basis='video_frame_count_over_fps'
        except (KeyError,TypeError,ValueError,ZeroDivisionError):pass
    if seconds is None and not any(x.get('codec_type')=='audio' for x in data.get('streams',[])):
        seconds=finite(data.get('format',{}).get('duration'));basis='container_duration_without_audio'
    if seconds is None:raise ValueError(f'Cannot establish {source_label} video duration independently of audio')
    if seconds<10:raise ValueError(f'{source_label} source video is shorter than10seconds ({seconds:.6f}); no repeat or time stretch')
    return {'video_duration_seconds':seconds,'duration_basis':basis,'short_source_policy':'reject_no_repeat_or_time_stretch','normalize_first_seconds':10,'target_fps':24,'target_frames':240}


def normal_green_candidate(source,output,work_dir,timing,ffmpeg='ffmpeg',ffprobe='ffprobe'):
    """Fixed Wan route: ordinary difference key, no global palette fitting."""
    if timing['video_duration_seconds']<10:raise ValueError('Wan source video is shorter than10seconds')
    report=convert(Path(source),Path(output),ffmpeg,ffprobe,Path(work_dir),False,lossless=True)
    report['green_source_processing']={'worker_version':WAN_WORKER_VERSION,'processing_profile':WAN_PROFILE,
        'source_sha256':sha(source),'source_timing':timing,'global_palette_fitting':False,'white_classifier_used':False,
        'individual_skin_eye_edits':False,'geometry_warped':False,'short_phase_loop_used':False,
        'new_model_calls':0,'final_visual_review_required':True}
    Path(output).with_suffix('.report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def normal_u24_green_candidate(source,output,work_dir,timing,ffmpeg='ffmpeg',ffprobe='ffprobe'):
    """U24-only ordinary green key; no palette fit or semantic/white classifier."""
    if timing['video_duration_seconds']<10:raise ValueError('H3 U24 source video is shorter than10seconds')
    report=convert(Path(source),Path(output),ffmpeg,ffprobe,Path(work_dir),False,lossless=True)
    report['green_source_processing']={'worker_version':U24_WORKER_VERSION,'processing_profile':U24_PROFILE,
        'model_id':U24_MODEL_ID,'model_slug':U24_MODEL_SLUG,'source_sha256':sha(source),'source_timing':timing,
        'global_palette_fitting':False,'white_classifier_used':False,'semantic_segmentation_used':False,
        'individual_skin_eye_edits':False,'geometry_warped':False,'short_phase_loop_used':False,
        'new_model_calls':0,'final_visual_review_required':True}
    Path(output).with_suffix('.report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scan_green_source(source,ffmpeg='ffmpeg',ffprobe='ffprobe'):
    return scan_source_background(source,'green',ffmpeg,ffprobe)


def decode_palette_frames(source,ffmpeg='ffmpeg'):
    # A bounded 640x360 fitting proxy; it never becomes the output geometry.
    raw=subprocess.check_output([ffmpeg,'-v','error','-i',str(source),'-t','10','-an',
        '-vf','fps=24,scale=640:360','-f','rawvideo','-pix_fmt','rgb24','-'])
    frames=np.frombuffer(raw,np.uint8).reshape(-1,360,640,3)
    if len(frames)!=240:raise ValueError('Expected all 240 original source frames')
    return frames


def bound_palette_track(frames,track):
    """Reject a recoloring job that exceeds mild global correction bounds."""
    if track.shape!=(len(frames),4,3) or not np.isfinite(track).all():raise ValueError('Invalid palette track')
    if np.abs(track[:,:3]-np.eye(3)).max()>.65 or np.abs(track[:,3]).max()>.10:
        raise ValueError('Palette transform exceeds conservative matrix/offset limits')
    records=[]
    for i,(rgb,matrix) in enumerate(zip(frames,track)):
        mask=key_green(rgb)[...,3]>245
        mask=cv2.erode(mask.astype(np.uint8),np.ones((5,5),np.uint8))>0
        corrected=transform_rgb(rgb,matrix)
        delta=np.abs(corrected.astype(np.int16)-rgb)
        values=delta[mask]
        if not len(values):raise ValueError('No opaque material for palette safety check')
        p95=float(np.percentile(values,95));maximum=int(values.max())
        if p95>20 or maximum>40:
            raise ValueError(f'Palette correction is not mild at frame {i}: p95={p95:.1f}, max={maximum}')
        records.append({'frame':i,'foreground_rgb_delta_p95':p95,'foreground_rgb_delta_max':maximum})
    return {'max_foreground_rgb_delta_p95':max(r['foreground_rgb_delta_p95'] for r in records),
        'max_foreground_rgb_delta':max(r['foreground_rgb_delta_max'] for r in records),
        'matrix_deviation_limit':.65,'offset_limit':.10,'rgb_p95_limit':20,'rgb_max_limit':40,
        'geometry_warped':False,'individual_face_skin_eye_edits':False,'frames':records}


class ConnectedGreenMatte:
    """A green chroma matte with edge-connected GREEN backdrop clearance.

    Correct materials before keying, retaining opaque white lace. No white
    flood fill, face/ear masks, component painting or silhouette replacement.
    Saturated green in enclosed hair gaps is removed by the chroma key itself.
    """
    name='bounded_prekey_palette_and_connected_green_background_v1'
    def __init__(self,track):self.track=track;self.stats=[]

    def __call__(self,rgb,index):
        corrected=transform_rgb(rgb,self.track[min(index,len(self.track)-1)])
        rgba=key_green(corrected,low=12,high=110)
        color=corrected.astype(np.int16)
        green=(color[...,1]-np.maximum(color[...,0],color[...,2])>18)&(color[...,1]>100)
        padded=np.pad(green.astype(np.uint8),1,constant_values=1)
        cv2.floodFill(padded,None,(0,0),2)
        background=padded[1:-1,1:-1]==2
        depth=cv2.distanceTransform((~background).astype(np.uint8),cv2.DIST_L2,3)
        silhouette_alpha=np.rint(np.clip(depth/1.5,0,1)*255).astype(np.uint8)
        rgba[...,3]=np.minimum(rgba[...,3],silhouette_alpha)
        rgba[rgba[...,3]==0,:3]=0
        rgba,edge=despill_auburn_collar(rgba)
        opaque=(key_green(rgb)[...,3]>245)&(rgba[...,3]>245)
        delta=np.abs(rgba[...,:3].astype(np.int16)-rgb)
        values=delta[opaque]
        maximum=int(values.max()) if len(values) else 0
        p95=float(np.percentile(values,95)) if len(values) else 0
        if maximum>40 or p95>20:
            raise ValueError(f'Total global palette plus edge correction is not mild at frame {index}: p95={p95:.1f}, max={maximum}')
        self.stats.append({'frame':index,'connected_green_background_pixels':int(background.sum()),'edge_despill':edge,
            'total_opaque_rgb_delta_p95':p95,'total_opaque_rgb_delta_max':maximum})
        return rgba


def green_candidate(source,output,work_dir,ffmpeg='ffmpeg',ffprobe='ffprobe',palette_anchor_descriptor=None):
    canonical,anchor_provenance=select_palette_anchor(PACK,palette_anchor_descriptor)
    frames=decode_palette_frames(source,ffmpeg)
    track,fit_records=estimate_track(frames)
    data=subprocess.check_output([ffmpeg,'-v','error','-c:v','libvpx-vp9','-i',str(canonical),
        '-frames:v','1','-f','rawvideo','-pix_fmt','rgba','-'])
    reference=np.frombuffer(data,np.uint8).reshape(360,640,4)
    anchor,anchor_record=canonical_palette_anchor(frames[0],reference)
    track=compose_palette_track(track,anchor)
    safety=bound_palette_track(frames,track)
    matte=ConnectedGreenMatte(track)
    intermediate=Path(work_dir)/'green-matte.webm'
    convert(Path(source),intermediate,ffmpeg,ffprobe,Path(work_dir)/'render',True,frame_matte=matte,lossless=True)
    # Proven neutral-material pass, preserving the decoded input Alpha plane.
    report=neutral_only(intermediate,Path(output),ffmpeg,ffprobe)
    report['green_source_processing']={'source_sha256':sha(source),'white_classifier_used':False,
        'source_timing_preserved':True,'short_phase_loop_used':False,'geometry_warped':False,
        'individual_skin_eye_edits':False,'key_after_palette':True,'new_model_calls':0,
        'palette_safety':{k:v for k,v in safety.items() if k!='frames'},'final_visual_review_required':True}
    report['green_source_processing']['worker_version']=WORKER_VERSION
    report['green_source_processing']['canonical_palette_anchor']={'reference_sha256':sha(canonical),'reference_frame':0,**anchor_record,'provenance':anchor_provenance}
    Path(output).with_suffix('.report.json').write_text(json.dumps(report,indent=2)+'\n')
    Path(output).with_suffix('.palette.json').write_text(json.dumps({'source_sha256':sha(source),
        'fit':fit_records,'canonical_anchor':anchor_record,'safety':safety,'green_matte':matte.stats,'new_model_calls':0},indent=2)+'\n')
    return report


def process_snapshot(client,action_snapshot,attempt_snapshot,attempt_index,claim_token):
    """Return an immutable attempt patch. Caller owns all state CAS/approval."""
    cv2.setNumThreads(1)
    a=copy.deepcopy(action_snapshot);attempt=copy.deepcopy(attempt_snapshot)
    if not re.fullmatch(r'a\d{3}',a['id']) or not isinstance(attempt_index,int) or attempt_index<1:
        raise ValueError('Invalid action/attempt identity')
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,80}',claim_token):raise ValueError('Invalid media claim token')
    name=a['name']
    if Path(name).name!=name or '/' in name or '\\' in name:raise ValueError('Unsafe action filename')
    folder=PACK/'source/library'/a['id']/f'attempt-{attempt_index}'
    folder.mkdir(parents=True,exist_ok=True)
    raw=folder/(name+'.mp4');claim=folder/('processing-'+claim_token);claim.mkdir(exist_ok=True)
    patch={'worker_version':WORKER_VERSION};result={'attempt_patch':patch,'action_status':'processing_failed','hard_defect':False,
        'task_id':attempt.get('task_id'),'attempt_index':attempt_index,'claim_token':claim_token}
    try:
        chroma=attempt.get('chroma_background','green')
        if not isinstance(chroma,str) or chroma not in {'green','blue'}:
            raise ValueError('Unsupported approved chroma background; expected green or blue')
        if not raw.exists():
            partial=raw.with_suffix('.download.'+claim_token)
            with client.files.download_file(asset_id=attempt['result_asset_id']) as data:data.save(partial)
            if not raw.exists():partial.replace(raw)
            else:partial.unlink(missing_ok=True)
        digest=sha(raw);patch.update({'source_file':str(raw.relative_to(PACK)),'source_sha256':digest})
        profile=None
        if chroma=='green':
            profile=processing_profile(attempt)
            if profile!=U24_PROFILE and 'palette_anchor_descriptor' in attempt and attempt['palette_anchor_descriptor'] is None:
                raise ValueError('Declared palette anchor descriptor may not be null')
            if profile==WAN_PROFILE:
                patch.update(worker_version=WAN_WORKER_VERSION,processing_profile=WAN_PROFILE,source_video_timing=require_ten_seconds_video(raw))
            elif profile==U24_PROFILE:
                patch.update(worker_version=U24_WORKER_VERSION,processing_profile=U24_PROFILE,
                    source_video_timing=require_ten_seconds_video(raw,source_label='H3 U24'))
        else:
            patch.update(worker_version=BLUE_SOURCE_WORKER_VERSION,blue_source_recovery_only=True)
        contact=claim/'source-contact.png'
        select='+'.join('eq(n\\,'+str(n)+')' for n in list(range(0,240,24))+[239])
        subprocess.run(['ffmpeg','-y','-v','error','-i',str(raw),'-vf',
            f'fps=24,select={select},scale=320:-2,tile=4x3:nb_frames=11:padding=4:color=white',
            '-frames:v','1',str(contact)],check=True)
        patch['contact']=str(contact)
        patch['source_background']=(scan_green_source(raw) if chroma=='green'
            else scan_source_background(raw,chroma))
        review_path=source_review_path(PACK,a['id'],attempt_index)
        try:
            stat=review_path.stat();patch['source_review_fingerprint']=f'{stat.st_mtime_ns}:{stat.st_size}'
        except FileNotFoundError:patch['source_review_fingerprint']=None
        review=load_source_review(PACK,a['id'],attempt_index,digest);patch['source_quality']=review
        if not patch['source_background']['passed']:
            patch['processing_error']=f'Source does not retain a stable saturated {chroma} backdrop for all 240 frames'
            result['hard_defect']=True;result['defect_kind']='background';return result
        if review['processing_clearance']=='reject':
            patch['processing_error']='Independent source review rejected hard visual defects: '+review.get('reason','see source_quality')
            kinds=[d.get('type','source_quality') for d in review.get('defects',[]) if d.get('severity')=='hard']
            result['defect_kind']='foreground_lighting' if any(any(word in kind for word in ['light','glow','bokeh','spot','fx']) for kind in kinds) else (kinds[0] if kinds else 'source_quality')
            result['hard_defect']=True;return result
        if chroma=='blue':
            # An explicit BLUE probe may recover/inspect its original result,
            # but no blue-to-alpha media recipe is approved in this worker.
            patch['processing_notice']='Blue source recovery and native background review only; green key/palette/semantic processing disabled'
            result['action_status']='awaiting_source_review';return result
        if review['processing_clearance']!=ALLOW:
            result['action_status']='awaiting_source_review';return result
        candidate=claim/(name+'.webm')
        if profile==WAN_PROFILE:report=normal_green_candidate(raw,candidate,claim/'work',patch['source_video_timing'])
        elif profile==U24_PROFILE:report=normal_u24_green_candidate(raw,candidate,claim/'work',patch['source_video_timing'])
        else:report=green_candidate(raw,candidate,claim/'work',palette_anchor_descriptor=attempt.get('palette_anchor_descriptor'))
        if sha(raw)!=digest:raise RuntimeError('Source bytes changed during processing; result must be quarantined')
        patch.update({'candidate_file':str(candidate.relative_to(PACK)),'candidate_sha256':sha(candidate),'report':report,
            'processing_error':None,'processing_method':patch['worker_version']})
        alpha_contact=claim/'alpha-three-backgrounds.png'
        subprocess.run([sys.executable,str(ROOT/'scripts/kurisu_review_contact.py'),str(candidate),str(alpha_contact)],check=True)
        patch['alpha_contact']=str(alpha_contact)
        result['action_status']='awaiting_review'
    except Exception as exc:
        # The detached queue owns per-task backoff and crash recovery. A known
        # paid result must remain retryable after transient I/O; do not flatten
        # a download/transport failure into a terminal processing result.
        transient=(isinstance(exc,(OSError,TimeoutError,ConnectionError)) or type(exc).__name__ in {
            'ConnectError','ReadTimeout','WriteTimeout','ConnectTimeout','PoolTimeout',
            'ReadError','WriteError','RemoteProtocolError'})
        status=getattr(exc,'status_code',None) or getattr(getattr(exc,'response',None),'status_code',None)
        if transient or status in {408,429,500,502,503,504}:raise
        patch['processing_error']=f'{type(exc).__name__}: {exc}'
    return result


if __name__=='__main__':
    cv2.setNumThreads(1)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,required=True);parser.add_argument('--result',type=Path,required=True)
    args=parser.parse_args();snapshot=json.loads(args.snapshot.read_text())
    from future_props_lab.desktop import desktop_client
    with desktop_client() as client:
        result=process_snapshot(client,snapshot['action'],snapshot['attempt'],snapshot['attempt_index'],snapshot['claim_token'])
    args.result.parent.mkdir(parents=True,exist_ok=True);temp=args.result.with_suffix('.next.json')
    temp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');temp.replace(args.result)
    print(json.dumps({'action':snapshot['action']['id'],'action_status':result['action_status'],'hard_defect':result['hard_defect']},ensure_ascii=False))
