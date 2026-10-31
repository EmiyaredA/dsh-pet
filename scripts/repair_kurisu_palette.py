#!/usr/bin/env python3
"""Restore an inspected green-source clip's temporal palette before green keying.

Explicit offline repair only: no ledger writes, no generation, no geometry edits.
The first clean SOURCE frame supplies the palette; use an already repaired
source when a documented opening-fade repair exists. Optical flow is used only
for fitting corresponding colors; no output frame or alpha is warped.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import cv2
import numpy as np
from build_pet_pack import convert,key_green,read_frame,verify_output,measure

IDENTITY=np.vstack([np.eye(3),np.zeros(3)]).astype(np.float32)


def material_masks(reference):
    rgb=reference.astype(np.float32)
    opaque=key_green(reference)[...,3]>250
    opaque=cv2.erode(opaque.astype(np.uint8),np.ones((5,5),np.uint8))>0
    # Exclude outlines, eyes and skin from fitting. Color application is global
    # on the source foreground; its transform must remain close to identity.
    gray=cv2.cvtColor(reference,cv2.COLOR_RGB2GRAY).astype(np.float32)
    gradient=np.abs(cv2.Sobel(gray,cv2.CV_32F,1,0))+np.abs(cv2.Sobel(gray,cv2.CV_32F,0,1))
    opaque&=gradient<60
    red=(rgb[...,0]>80)&(rgb[...,0]-rgb[...,1]>35)&(rgb[...,0]-rgb[...,2]>35)
    white=(rgb.min(2)>180)&(np.ptp(rgb,axis=2)<35)
    neutral=(rgb.max(2)<120)&(np.ptp(rgb,axis=2)<30)
    return [opaque&red,opaque&white,opaque&neutral]


def fit_palette_transform(current,target,masks):
    """Balanced robust affine RGB fit; colors are normalized to [0,1]."""
    cur=current.astype(np.float32)/255;ref=target.astype(np.float32)/255
    valid=(np.abs(cur-ref).max(2)<.30)&(key_green(current)[...,3]>245)
    arrays=[];goals=[];weights=[]
    for mask in masks:
        mask=mask&valid
        n=int(mask.sum())
        if n<16:continue
        arrays.append(cur[mask]);goals.append(ref[mask]);weights.append(np.full(n,1/n,np.float32))
    if len(arrays)<2:return IDENTITY.copy(),{'fit_pixels':0,'identity_fallback':True}
    a=np.concatenate(arrays);b=np.concatenate(goals);prior=np.concatenate(weights)
    a=np.column_stack([a,np.ones(len(a),np.float32)])
    weight=prior.copy()
    # Mild identity regularization prevents the RGB matrix from recoloring
    # unseen hues excessively when the neutral/hair samples are correlated.
    reg=.0005
    for _ in range(5):
        m=np.linalg.solve(a.T@(a*weight[:,None])+reg*np.eye(4),a.T@(b*weight[:,None])+reg*IDENTITY)
        error=np.linalg.norm(a@m-b,axis=1)
        weight=prior*np.minimum(1,.025/np.maximum(error,1e-6))
    if not np.isfinite(m).all() or np.max(np.abs(m[:3]-np.eye(3)))>.9 or np.max(np.abs(m[3]))>.15:
        raise ValueError('Temporal palette fit is too large or ill-conditioned')
    return m.astype(np.float32),{'fit_pixels':len(a),'median_fit_rgb_error':float(np.median(np.abs(a@m-b))*255)}


def estimate_track(frames):
    reference=frames[0];masks=material_masks(reference)
    foreground=key_green(reference)[...,3]>245
    ref_gray=cv2.cvtColor(reference,cv2.COLOR_RGB2GRAY);ref_gray[~foreground]=0
    yy,xx=np.indices(ref_gray.shape,dtype=np.float32)
    matrices=[];records=[]
    for i,current in enumerate(frames):
        if i==0:
            matrices.append(IDENTITY.copy());records.append({'frame':0,'fit_pixels':sum(int(m.sum()) for m in masks),'median_fit_rgb_error':0});continue
        gray=cv2.cvtColor(current,cv2.COLOR_RGB2GRAY)
        gray[key_green(current)[...,3]<245]=0
        flow=cv2.calcOpticalFlowFarneback(gray,ref_gray,None,.5,3,21,4,7,1.5,0)
        mx=xx+flow[...,0];my=yy+flow[...,1]
        target=cv2.remap(reference,mx,my,cv2.INTER_LINEAR)
        mapped=[cv2.remap(m.astype(np.uint8),mx,my,cv2.INTER_NEAREST)>0 for m in masks]
        matrix,record=fit_palette_transform(current,target,mapped)
        matrices.append(matrix);records.append({'frame':i,**record})
    # Symmetric short smoothing suppresses coefficient chatter. Keep the exact
    # pristine opening frame and preserve the source's original 240-frame timing.
    track=np.asarray(matrices);smooth=track.copy();kernel=np.array([1,2,3,2,1],np.float32)
    padded=np.pad(track,((2,2),(0,0),(0,0)),mode='edge')
    for i in range(len(track)):smooth[i]=(padded[i:i+5]*kernel[:,None,None]).sum(0)/kernel.sum()
    smooth[0]=IDENTITY
    for i,record in enumerate(records):record['matrix']=smooth[i].tolist()
    return smooth,records


def transform_rgb(rgb,matrix):
    # Apply before the green-removal clamp, which irreversibly clips the G data.
    corrected=(rgb.astype(np.float32)/255)@matrix[:3]+matrix[3]
    corrected=np.clip(corrected*255,0,255)
    # Residual spatial spill on the neutral white lace cannot be represented
    # by one affine matrix. Remove positive green chroma only from this bright
    # near-neutral material, conserving luminance approximately. Auburn hair,
    # skin, blue eyes and the saturated green backdrop cannot enter this mask.
    r,g,b=corrected[...,0],corrected[...,1],corrected[...,2]
    white=(np.minimum(r,b)>160)&(np.abs(r-b)<32)&(g-(r+b)/2>3)
    # The nominal first frame can already contain green spill on lace. Do not
    # preserve that defect merely because its temporal matrix is identity.
    amount=np.clip(g-(r+b)/2-1,0,30)*white
    corrected[...,0]+=.6*amount
    corrected[...,1]-=.4*amount
    corrected[...,2]+=.6*amount
    # A +4 green tolerance is visible as olive on very dark stockings/shoes.
    # Neutralize only positive green in dark, nearly achromatic materials.
    # Red hair, skin, blue eyes and the saturated backdrop cannot qualify.
    r,g,b=corrected[...,0],corrected[...,1],corrected[...,2]
    dark=(np.minimum(r,b)>8)&(corrected.max(2)<110)&(np.abs(r-b)<12)&(g>np.maximum(r,b)+2)
    corrected[...,1][dark]=(r[dark]+b[dark])/2+1
    corrected=np.rint(np.clip(corrected,0,255)).astype(np.uint8)
    # The digital backdrop is not a photographed material; leave it unchanged.
    color=rgb.astype(np.int16)
    background=(color[...,1]-np.maximum(color[...,0],color[...,2])>70)&(color[...,1]>140)
    corrected[background]=rgb[background]
    return corrected


def compose_palette_track(track,anchor):
    """Compose two global affine RGB transforms, without touching geometry."""
    combined=track.copy()
    combined[:,:3]=track[:,:3]@anchor[:3]
    combined[:,3]=track[:,3]@anchor[:3]+anchor[3]
    return combined


def canonical_palette_anchor(source_first,reference_rgba):
    """Fit source colors to a qualified canonical frame; alignment is fit-only.

    Pink and blue materials participate in ONE global affine RGB fit. No eye,
    face, skin or other material receives its own output transform or repaint.
    """
    rgb=reference_rgba[...,:3];alpha=reference_rgba[...,3]
    src_box=measure(key_green(source_first)[...,3]);ref_box=measure(alpha)
    factor=src_box['height']/ref_box['height']
    tx=src_box['center_x']-factor*ref_box['center_x'];ty=src_box['feet_y']-factor*ref_box['feet_y']
    h,w=source_first.shape[:2];warp=np.array([[factor,0,tx],[0,factor,ty]],np.float32)
    bg=np.median(np.concatenate([source_first[0],source_first[-1],source_first[:,0],source_first[:,-1]]),axis=0)
    a=alpha[...,None].astype(np.float32)/255
    composite=np.rint(rgb*a+bg*(1-a)).astype(np.uint8)
    target=cv2.warpAffine(composite,warp,(w,h),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=tuple(float(v) for v in bg))
    ref_masks=material_masks(composite)
    opaque=cv2.erode((alpha>245).astype(np.uint8),np.ones((5,5),np.uint8))>0
    yy=np.indices(alpha.shape)[0];rr=rgb.astype(np.int16)
    head_y=(yy-ref_box['box'][1])/ref_box['height']
    blue=opaque&(rr[...,2]>rr[...,0]+15)&(rr[...,2]>rr[...,1]+5)&(rr[...,2]>75)&(rr[...,0]<180)&(head_y>.30)&(head_y<.52)
    pink=opaque&(rr[...,0]>150)&(rr[...,0]-rr[...,1]>30)&(rr[...,2]-rr[...,1]>8)
    ref_masks.extend([blue,pink&(head_y<.20),pink&(head_y>=.20)])
    names=['auburn_hair','white_fabric','dark_neutral','blue_iris_material','pink_ear_material','pink_bow_material']
    masks=[cv2.warpAffine(m.astype(np.uint8),warp,(w,h),flags=cv2.INTER_NEAREST)>0 for m in ref_masks]
    # Optical flow matches samples only. Neither this warp nor the flow is ever
    # used to render an output frame or an output alpha plane.
    sg=cv2.cvtColor(source_first,cv2.COLOR_RGB2GRAY);tg=cv2.cvtColor(target,cv2.COLOR_RGB2GRAY)
    sg[key_green(source_first)[...,3]<245]=0;tg[key_green(target)[...,3]<245]=0
    flow=cv2.calcOpticalFlowFarneback(sg,tg,None,.5,3,21,4,7,1.5,0)
    y,x=np.indices((h,w),dtype=np.float32);mx=x+flow[...,0];my=y+flow[...,1]
    target=cv2.remap(target,mx,my,cv2.INTER_LINEAR)
    masks=[cv2.remap(m.astype(np.uint8),mx,my,cv2.INTER_NEAREST)>0 for m in masks]
    matrix,fit=fit_palette_transform(source_first,target,masks)
    corrected=transform_rgb(source_first,matrix);records={}
    valid=key_green(source_first)[...,3]>245
    for name,mask in zip(names,masks):
        mask=mask&valid
        if int(mask.sum())<8:continue
        before=np.median(source_first[mask],axis=0);after=np.median(corrected[mask],axis=0);goal=np.median(target[mask],axis=0)
        records[name]={'samples':int(mask.sum()),'source_median_rgb':before.tolist(),'corrected_median_rgb':after.tolist(),
            'canonical_median_rgb':goal.tolist(),'before_max_channel_error':float(np.max(np.abs(before-goal))),
            'after_max_channel_error':float(np.max(np.abs(after-goal)))}
    return matrix,{'matrix':matrix.tolist(),'fit':fit,'materials':records,'fit_only_alignment':{'scale':factor,'translation':[tx,ty]},
        'output_geometry_warped':False,'per_material_output_edits':False}


class TemporalPaletteMatte:
    name='original_source_temporal_palette_with_unchanged_geometry'
    def __init__(self,track,despill=True):self.track=track;self.despill=despill
    def __call__(self,rgb,index):
        original_alpha=key_green(rgb)[...,3]
        corrected=transform_rgb(rgb,self.track[min(index,len(self.track)-1)])
        rgba=key_green(corrected)
        # Palette correction must not expand/erode a single source alpha pixel.
        rgba[...,3]=original_alpha
        if self.despill:
            from kurisu_hair_matte import despill_boundary
            rgba,_=despill_boundary(rgba)
        rgba[original_alpha==0,:3]=0
        return rgba


def repair(source,output,ffmpeg,ffprobe,work_dir):
    data=subprocess.check_output([ffmpeg,'-v','error','-i',str(source),'-t','10','-vf','fps=24,scale=640:-2','-an','-f','rawvideo','-pix_fmt','rgb24','-'])
    probe=json.loads(subprocess.check_output([ffprobe,'-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','json',str(source)]))['streams'][0]
    height=round(probe['height']*640/probe['width']/2)*2
    frames=np.frombuffer(data,np.uint8).reshape(-1,height,640,3)
    if len(frames)!=240:raise ValueError('Expected 240 source frames at 24fps')
    track,records=estimate_track(frames)
    report=convert(source,output,ffmpeg,ffprobe,work_dir,True,frame_matte=TemporalPaletteMatte(track),lossless=True)
    report['temporal_palette']={'anchor':'source frame 0','source_timing_preserved':True,'geometry_warped':False,'source_alpha_unchanged':True,'new_model_calls':0}
    output.with_suffix('.report.json').write_text(json.dumps(report,indent=2)+'\n')
    output.with_suffix('.palette.json').write_text(json.dumps({'source':str(source),'anchor_frame':0,'records':records,'new_model_calls':0},indent=2)+'\n')
    return report


def neutral_only(source,output,ffmpeg,ffprobe):
    """Remove positive-green neutral-material cast from an existing RGBA clip.

    Reattach the ORIGINAL alpha plane after color conversion. Passing RGBA
    straight into swscale's YUVA conversion can round alpha by one level even
    with a lossless codec. Decode and compare all 240 alpha planes afterward.
    """
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    code_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output.parent.mkdir(parents=True,exist_ok=True)
    decode=lambda path:subprocess.Popen([ffmpeg,'-v','error','-c:v','libvpx-vp9','-i',str(path),
        '-f','rawvideo','-pix_fmt','rgba','-'],stdout=subprocess.PIPE)
    decoder=decode(source)
    filters='[0:v]split=2[color][alpha];[color]format=yuv420p[color420];[alpha]alphaextract[mask];[color420][mask]alphamerge[out]'
    encoder=subprocess.Popen([ffmpeg,'-y','-v','error','-f','rawvideo','-pix_fmt','rgba','-s','640x360','-r','24','-i','-',
        '-filter_complex',filters,'-map','[out]','-an','-c:v','libvpx-vp9','-pix_fmt','yuva420p',
        '-lossless','1','-auto-alt-ref','0','-b:v','0','-crf','0','-row-mt','1','-threads','3','-cpu-used','4',str(output)],stdin=subprocess.PIPE)
    frames=0;changed=0
    try:
        while data:=read_frame(decoder.stdout,640*360*4):
            rgba=np.frombuffer(data,np.uint8).reshape(360,640,4);result=rgba.copy()
            result[...,:3]=transform_rgb(rgba[...,:3],IDENTITY)
            result[result[...,3]==0,:3]=0
            changed+=int(np.count_nonzero(np.any(result[...,:3]!=rgba[...,:3],axis=2)))
            encoder.stdin.write(result.tobytes());frames+=1
    finally:
        decoder.stdout.close();encoder.stdin.close();dr=decoder.wait();er=encoder.wait()
    if frames!=240 or dr or er:raise ValueError('Neutral RGBA repair requires 240 correctly decoded frames')
    verification=verify_output(output,ffmpeg,ffprobe)
    before=decode(source);after=decode(output);max_delta=0
    try:
        for _ in range(240):
            a=np.frombuffer(read_frame(before.stdout,640*360*4),np.uint8).reshape(360,640,4)[...,3]
            b=np.frombuffer(read_frame(after.stdout,640*360*4),np.uint8).reshape(360,640,4)[...,3]
            max_delta=max(max_delta,int(np.abs(a.astype(np.int16)-b).max()))
    finally:
        before.stdout.close();after.stdout.close();before.wait();after.wait()
    if max_delta:raise ValueError(f'Neutral-only repair changed decoded alpha by {max_delta}')
    old_report=source.with_suffix('.report.json')
    report=json.loads(old_report.read_text()) if old_report.exists() else {}
    report.update({'output':output.name,'verification':verification,'encoding_lossless':True,
        'neutral_material_revision':{'type':'positive_green_neutral_white_and_dark_materials',
            'input':str(source),'input_sha256':digest,'algorithm_sha256':code_sha,
            'changed_rgb_pixels_all_frames':changed,'decoded_alpha_byte_exact':True,
            'alpha_encoding':'extract_original_plane_and_alphamerge_after_color_conversion','new_model_calls':0}})
    output.with_suffix('.report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    cv2.setNumThreads(1)
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--ffmpeg',default=shutil.which('ffmpeg'));p.add_argument('--ffprobe',default=shutil.which('ffprobe'));p.add_argument('--work-dir',type=Path,default=Path('temp/kurisu/render'))
    p.add_argument('--neutral-only',action='store_true',help='Existing RGBA WebM: neutral-material color repair with byte-exact original alpha')
    args=p.parse_args();report=neutral_only(args.input,args.output,args.ffmpeg,args.ffprobe) if args.neutral_only else repair(args.input,args.output,args.ffmpeg,args.ffprobe,args.work_dir)
    print(json.dumps(report,ensure_ascii=False))
