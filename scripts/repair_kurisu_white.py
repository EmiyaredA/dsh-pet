#!/usr/bin/env python3
"""Matte an outlined white-background gait result without erasing white lace.

Requires OpenCV in an isolated environment. Keeps edge-enclosed costume whites;
an optional, tightly scoped gray-tail cleanup applies only to these no-prop gaits.
"""
import argparse
import json
from pathlib import Path
import shutil
import cv2
import numpy as np
from kurisu_library import load,save,production_lock,PACK,ROOT,convert,now
from build_pet_pack import measure,key_green


class WhiteConnectedMatte:
    name='edge_connected_white_with_outline_protection'

    def __init__(self,remove_tail=False,allow_green=False):
        self.remove_tail=remove_tail
        self.allow_green=allow_green
        if allow_green:self.name='edge_connected_green_or_white_with_outline_protection'
        self.removed_pixels=0
        self.background_samples=[]

    def __call__(self,rgb,index):
        h,w=rgb.shape[:2]
        bg=np.median(np.concatenate([rgb[0],rgb[-1],rgb[:,0],rgb[:,-1]]),axis=0)
        white=bg.min()>=220 and bg.max()-bg.min()<=30
        green=bg[1]-max(bg[0],bg[2])>24 and bg[1]>180
        if not (white or (self.allow_green and green)):
            raise ValueError('Expected a flat near-white or expressly allowed green background')
        frame=rgb.copy()
        if len(self.background_samples)<3:self.background_samples.append(bg.tolist())
        if self.remove_tail and 18<=index<=190:
            values=frame.astype(np.int16)
            neutral=(values.max(2)-values.min(2)<20)&(values.min(2)>45)&(values.max(2)<140)
            roi=np.zeros((h,w),np.uint8)
            roi[int(.68*h):int(.83*h),int(.55*w):int(.67*w)]=1
            count,labels,stats,_=cv2.connectedComponentsWithStats((neutral&roi.astype(bool)).astype(np.uint8),connectivity=8)
            tail=np.zeros((h,w),np.uint8)
            for label in range(1,count):
                _,_,cw,ch,area=stats[label]
                if area>=12 and cw>1.5*ch:tail[labels==label]=1
            tail=cv2.dilate(tail,np.ones((3,3),np.uint8))&roi
            self.removed_pixels+=int(tail.sum())
            frame[tail.astype(bool)]=bg.astype(np.uint8)
        near=(np.abs(frame.astype(np.int16)-bg).max(2)<=24).astype(np.uint8)
        padded=np.pad(near,1,constant_values=1)
        cv2.floodFill(padded,None,(0,0),2)
        foreground=(padded[1:-1,1:-1]!=2).astype(np.uint8)
        if self.remove_tail:
            count,labels,stats,_=cv2.connectedComponentsWithStats(foreground,connectivity=8)
            if count<2:raise ValueError('No character silhouette found')
            foreground=(labels==(1+np.argmax(stats[1:,cv2.CC_STAT_AREA]))).astype(np.uint8)
        distance=cv2.distanceTransform(foreground,cv2.DIST_L2,3)
        alpha=np.clip(distance/1.5,0,1)
        color=frame.astype(np.float32)
        edge=(alpha>0)&(alpha<1)
        color[edge]=(color[edge]-bg*(1-alpha[edge,None]))/alpha[edge,None]
        rgba=np.dstack([np.clip(color,0,255).astype(np.uint8),np.rint(alpha*255).astype(np.uint8)])
        if self.allow_green:
            if green:
                chroma=key_green(frame,low=8,high=max(16,min(220,float(bg[1]-max(bg[0],bg[2]))*.85)))
                rgba[...,3]=np.minimum(rgba[...,3],chroma[...,3])
            # Neutralize spill, including green trapped in outline-enclosed hair gaps.
            rgba[...,1]=np.minimum(rgba[...,1],np.minimum(255,np.maximum(rgba[...,0].astype(np.uint16),rgba[...,2])+4)).astype(np.uint8)
        rgba[rgba[...,3]==0,:3]=0
        return rgba


class WhiteStandingMatte(WhiteConnectedMatte):
    """Undo whole-figure zoom/translation for inspected, stationary no-prop shots.

    This must not be used for jumps, drags, walking, bows or changing silhouettes.
    It scales the entire RGBA image uniformly and never changes body proportions.
    """
    name='edge_connected_white_and_stationary_scale_alignment'

    def __init__(self,allow_green=False):
        super().__init__(allow_green=allow_green);self.anchor=None;self.scales=[]
        self.name='edge_connected_matte_and_stationary_scale_alignment'

    def __call__(self,rgb,index):
        rgba=super().__call__(rgb,index)
        item=measure(rgba[...,3])
        if self.anchor is None:self.anchor=item
        factor=self.anchor['height']/item['height'];self.scales.append(factor)
        tx=self.anchor['center_x']-factor*item['center_x']
        ty=self.anchor['feet_y']-factor*item['feet_y']
        alpha=rgba[...,3:4].astype(np.float32)/255
        premult=np.concatenate([rgba[...,:3]*alpha,rgba[...,3:4]],axis=2)
        warped=cv2.warpAffine(premult,np.array([[factor,0,tx],[0,factor,ty]],np.float32),
            (rgb.shape[1],rgb.shape[0]),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
        a=np.clip(warped[...,3:4],0,255)
        color=np.divide(warped[...,:3]*255,a,out=np.zeros_like(warped[...,:3]),where=a>0)
        return np.concatenate([np.clip(color,0,255),a],axis=2).astype(np.uint8)


def convert_white_source(source,output,remove_tail=False,stabilize_standing=False,allow_green=False):
    matte=WhiteStandingMatte(allow_green) if stabilize_standing else WhiteConnectedMatte(remove_tail,allow_green)
    report=convert(source,output,shutil.which('ffmpeg'),shutil.which('ffprobe'),ROOT/'temp/kurisu/render',True,frame_matte=matte,lossless=True)
    edit={'type':matte.name,'removed_gray_tail_pixels':matte.removed_pixels,
        'tail_roi':[.55,.68,.67,.83] if remove_tail else None,'background_samples':matte.background_samples,
        'edited_at':now(),'reason':'Use edge-connected matting with enclosed white costume protection for the observed flat '+('green/near-white transition' if allow_green else 'near-white background')
            + (' and scoped cleanup of the noncanonical gray appendage in a no-prop side gait' if remove_tail else '')}
    if stabilize_standing:
        edit['standing_stabilization']={'scale_range':[min(matte.scales),max(matte.scales)],
            'anchor':matte.anchor,'reason':'Stationary standing shot with props confined below the head contains supplier whole-figure zoom drift; uniform scaling and baseline translation only'}
    return report,edit


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--action');mode.add_argument('--input',type=Path)
    p.add_argument('--output',type=Path);p.add_argument('--remove-gray-tail',action='store_true')
    p.add_argument('--stabilize-standing',action='store_true')
    p.add_argument('--allow-green',action='store_true')
    args=p.parse_args()
    if args.input:
        if not args.output or args.remove_gray_tail:p.error('Offline mode requires --output and never removes character details')
        report,edit=convert_white_source(args.input,args.output,stabilize_standing=args.stabilize_standing,allow_green=args.allow_green)
        print(json.dumps({'report':report,'local_edit':edit}));raise SystemExit(0)
    with production_lock():
        s=load();a=next(a for a in s['actions'] if a['id']==args.action)
        assert a['status']=='awaiting_review'
        if args.remove_gray_tail:assert a['id'] in {'a009','a010'}
        if args.stabilize_standing:assert (a['id'] in {'a104','a105'} or a['group'] in {'余额','碎碎念'}) and not args.remove_gray_tail
        t=a['attempts'][-1];source=PACK/t['source_file'];output=source.parent/(a['name']+'.webm')
        report,edit=convert_white_source(source,output,args.remove_gray_tail,args.stabilize_standing,args.allow_green)
        t['candidate_file']=str(output.relative_to(PACK));t['report']=report;t.pop('processing_error',None)
        t['local_edit']=edit
        save(s);print({'action':a['id'],'gray_pixels_removed':edit['removed_gray_tail_pixels'],'new_model_calls':0})
