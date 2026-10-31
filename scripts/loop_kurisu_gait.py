#!/usr/bin/env python3
"""Repeat an inspected side-gait phase, preserving source frames and geometry.

No optical flow, interpolation, crossfade, generated frames, or geometry scaling.
Output is a 240-frame silent VP9 Alpha pet animation. Callers select the phase
only after inspecting its heading, motion and seam. Does not edit the ledger.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import numpy as np
from build_pet_pack import read_frame,verify_output

WIDTH,HEIGHT,FPS=640,360,24


def phase_indices(start,count,repeats,total_frames):
    if start<0 or count<2 or repeats<1 or start+count>total_frames:
        raise ValueError('Invalid inspected source phase')
    return list(range(start,start+count))*repeats


def decoded_frames(path,ffmpeg):
    process=subprocess.Popen([ffmpeg,'-v','error','-c:v','libvpx-vp9','-i',str(path),'-an','-f','rawvideo','-pix_fmt','rgba','-'],stdout=subprocess.PIPE)
    finished=False
    try:
        while data:=read_frame(process.stdout,WIDTH*HEIGHT*4):
            yield np.frombuffer(data,np.uint8).reshape(HEIGHT,WIDTH,4)
        finished=True
    finally:
        if not finished and process.poll() is None:
            process.terminate()
        process.stdout.close()
        rc=process.wait()
        if finished and rc:raise RuntimeError('Failed to decode RGBA input')


def frame_box(frame):
    y,x=np.where(frame[...,3]>127)
    if not len(x):raise ValueError('Empty gait frame')
    return [int(x.min()),int(y.min()),int(x.max()),int(y.max())]


def premult_mad(first,last):
    a=first[...,:3].astype(np.float32)*first[...,3:4]/255
    b=last[...,:3].astype(np.float32)*last[...,3:4]/255
    return float(np.abs(a-b).mean())


def loop_phase(source,output,start,count,repeats,ffmpeg,ffprobe):
    metadata=json.loads(subprocess.check_output([ffprobe,'-v','error','-select_streams','v:0','-show_entries','stream=width,height,r_frame_rate','-of','json',str(source)]))['streams'][0]
    if (metadata['width'],metadata['height'],metadata['r_frame_rate'])!=(WIDTH,HEIGHT,'24/1'):
        raise ValueError('Input must be a 640x360 24fps RGBA pet video')
    if count*repeats!=240:raise ValueError('Pet loop must contain exactly 240 frames')
    phase=[];total=0
    for i,frame in enumerate(decoded_frames(source,ffmpeg)):
        if start<=i<start+count:phase.append(frame.copy())
        total+=1
    indices=phase_indices(start,count,repeats,total)
    if len(phase)!=count:raise ValueError('Incomplete source phase')
    if any(int(f[...,3].min())!=0 or int(f[...,3].max())!=255 for f in phase):
        raise ValueError('Source phase lacks actual alpha')
    output.parent.mkdir(parents=True,exist_ok=True)
    partial=output.with_name(output.stem+'.partial.webm')
    encoder=subprocess.Popen([ffmpeg,'-y','-v','error','-f','rawvideo','-pix_fmt','rgba','-s',f'{WIDTH}x{HEIGHT}','-r',str(FPS),'-i','-',
        '-filter_complex','[0:v]split=2[color][mask];[color]format=yuv420p[yuv];[mask]alphaextract[a];[yuv][a]alphamerge[out]','-map','[out]','-an','-c:v','libvpx-vp9','-pix_fmt','yuva420p','-lossless','1','-auto-alt-ref','0','-b:v','0','-crf','0','-row-mt','1','-threads','4','-cpu-used','4',str(partial)],stdin=subprocess.PIPE)
    try:
        for index in indices:encoder.stdin.write(phase[index-start].tobytes())
    finally:
        encoder.stdin.close();rc=encoder.wait()
    if rc:raise RuntimeError('Failed to encode the side-gait loop')
    verification=verify_output(partial,ffmpeg,ffprobe)
    # Audit the encoded loop against its corresponding source phase. RGB may
    # change by codec RGB↔YUV420 rounding, but alpha and all bounds must match.
    max_alpha_error=0;max_box_delta=0;rgb_errors=[]
    for i,encoded in enumerate(decoded_frames(partial,ffmpeg)):
        original=phase[i%count]
        max_alpha_error=max(max_alpha_error,int(np.abs(encoded[...,3].astype(np.int16)-original[...,3]).max()))
        max_box_delta=max(max_box_delta,max(abs(x-y) for x,y in zip(frame_box(encoded),frame_box(original))))
        mask=(original[...,3]>127)
        rgb_errors.append(float(np.abs(encoded[...,:3].astype(np.int16)-original[...,:3])[mask].mean()))
    if max_alpha_error or max_box_delta:
        raise ValueError('Encoding altered selected phase alpha or geometry')
    if max(rgb_errors)>2:raise ValueError('Unexpected color loss in lossless phase encoding')
    source_report_path=source.with_suffix('.report.json')
    source_report=json.loads(source_report_path.read_text()) if source_report_path.exists() else {}
    step=[premult_mad(a,b) for a,b in zip(phase[:-1],phase[1:])]
    seam=premult_mad(phase[-1],phase[0]);boxes=[frame_box(f) for f in phase]
    record={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source':str(source.resolve()),
        'start_frame':start,'count':count,'repeats':repeats,'source_frame_indices':indices,
        'source_phase_rgba_sha256':[hashlib.sha256(f.tobytes()).hexdigest() for f in phase],
        'motion_mode':'continuous-left-profile','lead_seconds':0,'tail_seconds':0,
        'new_model_calls':0,'geometry_scaling':False,'frame_interpolation':False,'crossfade':False,
        'seam_premult_fullframe_mad':seam,'typical_step_premult_fullframe_mad':float(np.mean(step)),
        'seam_over_typical':seam/float(np.mean(step)),'max_internal_step_mad':max(step),
        'phase_height_range':[min(b[3]-b[1] for b in boxes),max(b[3]-b[1] for b in boxes)],
        'phase_feet_range':[min(b[3] for b in boxes),max(b[3] for b in boxes)],
        'encoded_vs_source':{'max_alpha_error':max_alpha_error,'max_box_delta_px':max_box_delta,'max_foreground_mean_rgb_error':max(rgb_errors)}}
    report={**source_report,'source':source.name,'output':output.name,'encoding_lossless':True,'verification':verification,'loop_repair':record}
    partial.replace(output)
    output.with_suffix('.report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--start',type=int,required=True);p.add_argument('--count',type=int,required=True);p.add_argument('--repeats',type=int,required=True)
    p.add_argument('--ffmpeg',default=shutil.which('ffmpeg'));p.add_argument('--ffprobe',default=shutil.which('ffprobe'))
    args=p.parse_args();report=loop_phase(args.input,args.output,args.start,args.count,args.repeats,args.ffmpeg,args.ffprobe)
    print(json.dumps({'verification':report['verification'],'loop_repair':{k:v for k,v in report['loop_repair'].items() if k not in {'source_frame_indices','source_phase_rgba_sha256'}}},ensure_ascii=False))
