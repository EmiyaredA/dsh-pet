#!/usr/bin/env python3
"""Restore the existing a001 idle's temporal palette before green keying.

Explicit offline repair only: no ledger writes, no generation, no geometry edits.
The pristine first SOURCE frame supplies the palette. Optical flow is used only
for fitting corresponding colors; no output frame or alpha is warped.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import cv2
import numpy as np
from build_pet_pack import convert,key_green

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
    amount=np.clip(g-(r+b)/2-1,0,30)*white*(np.max(np.abs(matrix-IDENTITY))>1e-4)
    corrected[...,0]+=.6*amount
    corrected[...,1]-=.4*amount
    corrected[...,2]+=.6*amount
    corrected=np.rint(np.clip(corrected,0,255)).astype(np.uint8)
    # The digital backdrop is not a photographed material; leave it unchanged.
    color=rgb.astype(np.int16)
    background=(color[...,1]-np.maximum(color[...,0],color[...,2])>70)&(color[...,1]>140)
    corrected[background]=rgb[background]
    return corrected


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


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--ffmpeg',default=shutil.which('ffmpeg'));p.add_argument('--ffprobe',default=shutil.which('ffprobe'));p.add_argument('--work-dir',type=Path,default=Path('temp/kurisu/render'))
    args=p.parse_args();print(json.dumps(repair(args.input,args.output,args.ffmpeg,args.ffprobe,args.work_dir),ensure_ascii=False))
