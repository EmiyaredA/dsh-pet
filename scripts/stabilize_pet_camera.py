#!/usr/bin/env python3
"""Remove gradual whole-frame camera drift without flattening a pet's gestures.

Fits a linear camera trajectory from neutral endpoint poses. Every video frame is
uniformly transformed by that trajectory, rather than fitted to its moving outline.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import cv2
import numpy as np
from build_pet_pack import convert,measure,probe
from repair_kurisu_white import WhiteConnectedMatte


class LinearCameraMatte(WhiteConnectedMatte):
    name='flat_matte_with_linear_endpoint_camera_stabilization'

    def __init__(self,start,end):
        super().__init__(allow_green=True)
        self.name='flat_matte_with_linear_endpoint_camera_stabilization'
        self.start,self.end=start,end
        ratio=end['height']/start['height']
        if not .75<=ratio<=1.35:raise ValueError('Endpoint scale difference is too large for this local camera correction')

    def align(self,rgba,index):
        t=index/239
        expected={key:self.start[key]+(self.end[key]-self.start[key])*t
                  for key in ['height','center_x','feet_y']}
        scale=self.start['height']/expected['height']
        dx=self.start['center_x']-scale*expected['center_x']
        dy=self.start['feet_y']-scale*expected['feet_y']
        alpha=rgba[...,3:4].astype(np.float32)/255
        premult=np.concatenate([rgba[...,:3]*alpha,rgba[...,3:4]],axis=2)
        warped=cv2.warpAffine(premult,np.array([[scale,0,dx],[0,scale,dy]],np.float32),
            (rgba.shape[1],rgba.shape[0]),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
        a=np.clip(warped[...,3:4],0,255)
        rgb=np.divide(warped[...,:3]*255,a,out=np.zeros_like(warped[...,:3]),where=a>0)
        return np.concatenate([np.clip(rgb,0,255),a],axis=2).astype(np.uint8)

    def __call__(self,rgb,index):
        return self.align(super().__call__(rgb,index),index)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--ffmpeg',default=shutil.which('ffmpeg'));p.add_argument('--ffprobe',default=shutil.which('ffprobe'))
    args=p.parse_args();stream=probe(args.input,args.ffprobe)['streams'][0];w,h=stream['width'],stream['height']
    raw=subprocess.check_output([args.ffmpeg,'-v','error','-i',str(args.input),'-vf',
        r'fps=24,select=eq(n\,0)+eq(n\,239)','-frames:v','2','-fps_mode','passthrough',
        '-f','rawvideo','-pix_fmt','rgb24','-'])
    frames=np.frombuffer(raw,np.uint8).reshape(2,h,w,3)
    key=WhiteConnectedMatte(allow_green=True)
    start,end=[measure(key(frame,i)[...,3]) for i,frame in zip([0,239],frames)]
    matte=LinearCameraMatte(start,end)
    report=convert(args.input,args.output,args.ffmpeg,args.ffprobe,args.output.parent/'render',True,frame_matte=matte,lossless=True)
    report['camera_stabilization']={'start':start,'end':end,'method':'linear uniform scale and baseline translation from neutral endpoint poses; intermediate pose motion preserved'}
    args.output.with_suffix('.report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'output':str(args.output),'endpoint_geometry':report['verification']['endpoint_geometry'],'new_model_calls':0}))
